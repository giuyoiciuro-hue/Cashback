const express = require('express');
const axios = require('axios');
const { MACD, RSI } = require('technicalindicators');
const fs = require('fs-extra');
const path = require('path');
const ccxt = require('ccxt');

const pLimit = (limit) => {
    let active = 0;
    const queue = [];
    const next = () => {
        active--;
        if (queue.length > 0) queue.shift()();
    };
    return (fn) => new Promise((resolve, reject) => {
        const run = async () => {
            active++;
            try { resolve(await fn()); }
            catch (err) { reject(err); }
            finally { next(); }
        };
        if (active < limit) run();
        else queue.push(run);
    });
};

const STABLE_SYMBOLS = [
    'USDT','USDC','BUSD','DAI','FDUSD','TUSD','USDP','USDD','GUSD','FRAX','LUSD','EURC','USDAI'
];

const binance = new ccxt.binance({ enableRateLimit: true });

const app = express();
const port = 5000;

const DATA_FILE = path.join(__dirname, 'last_results.json');
const RSI_DATA_FILE = path.join(__dirname, 'rsi_results.json');
const ARB_DATA_FILE = path.join(__dirname, 'arbitrage_results.json');
const SETTINGS_FILE = path.join(__dirname, 'settings.json');
const RSI_SETTINGS_FILE = path.join(__dirname, 'rsi_settings.json');

const limit = pLimit(10);

app.use(express.json());
app.use(express.static(__dirname));

/* -------------------------------------------------------
   IMPORTANT FIX
   تحويل BTCUSDT -> BTC/USDT فقط عند طلب البيانات
--------------------------------------------------------*/

function normalizeSymbol(symbol){
    if(symbol.includes('/')) return symbol;
    if(symbol.endsWith('USDT')){
        const base = symbol.slice(0,-4);
        return `${base}/USDT`;
    }
    return symbol;
}

async function getOHLCV(symbol, interval) {

    const timeframeMap = {
        '1h':'1h',
        '4h':'4h',
        '1d':'1d',
        '1w':'1w'
    };

    const tf = timeframeMap[interval] || '1d';

    const ccxtSymbol = normalizeSymbol(symbol);

    try {
        const ohlcv = await binance.fetchOHLCV(ccxtSymbol, tf, undefined, 100);
        return ohlcv;
    } catch (e) {
        console.error(`Error fetching OHLCV for ${ccxtSymbol}:`, e.message);
        return null;
    }
}

/* -------------------------------------------------------
   FILE STORAGE
--------------------------------------------------------*/

const saveResults = async (data,file=DATA_FILE)=>{
    await fs.writeJson(file,data);
};

const loadResults = async (file=DATA_FILE)=>{
    if(await fs.pathExists(file)) return await fs.readJson(file);
    return [];
};

const saveSettings = async (settings,file=SETTINGS_FILE)=>{
    await fs.writeJson(file,settings);
};

const loadSettings = async (file=SETTINGS_FILE)=>{
    if(await fs.pathExists(file)) return await fs.readJson(file);
    if(file===RSI_SETTINGS_FILE) return {intervals:['1d'],type:'30/70'};
    return {intervals:['1d'],type:'histogram'};
};

/* -------------------------------------------------------
   ROUTES
--------------------------------------------------------*/

app.get('/',(req,res)=>{
    res.sendFile(path.join(__dirname,'index.html'));
});

app.get('/settings',async(req,res)=>{
    res.json(await loadSettings());
});

app.post('/save-settings',async(req,res)=>{
    await saveSettings(req.body);
    res.json({success:true});
});

app.get('/rsi-settings',async(req,res)=>{
    res.json(await loadSettings(RSI_SETTINGS_FILE));
});

app.post('/save-rsi-settings',async(req,res)=>{
    await saveSettings(req.body,RSI_SETTINGS_FILE);
    res.json({success:true});
});

app.get('/last-results',async(req,res)=>{
    res.json(await loadResults());
});

app.get('/rsi-last-results',async(req,res)=>{
    res.json(await loadResults(RSI_DATA_FILE));
});

/* -------------------------------------------------------
   FORMAT TICKER
--------------------------------------------------------*/

function formatTicker(ticker){
    const symbol=ticker.symbol.replace('/','');
    return{
        symbol:symbol.endsWith('USDT')?symbol.slice(0,-4):symbol,
        id:ticker.symbol,
        currentPrice:ticker.last
    };
}

/* -------------------------------------------------------
   RSI ANALYSIS
--------------------------------------------------------*/

app.get('/analyze-rsi',async(req,res)=>{

const settings=await loadSettings(RSI_SETTINGS_FILE);
const intervals=(req.query.intervals||settings.intervals.join(',')).split(',');
const rsiType=req.query.type||settings.type;
const [lowerBound]=rsiType.split('/').map(Number);

try{

const tickers=await binance.fetchTickers();

const usdtTickers=Object.values(tickers)
.filter(t=>t.symbol&&t.symbol.endsWith('/USDT'));

const symbols=usdtTickers
.sort((a,b)=>(b.quoteVolume||0)-(a.quoteVolume||0))
.slice(0,50)
.map(formatTicker);

const resultsMap=new Map();

const analyzeSymbolRSI=async(coinData,interval)=>{

const {symbol}=coinData;
const ccxtSymbol=`${symbol}USDT`;

try{

const ohlcv=await getOHLCV(ccxtSymbol,interval);
if(!ohlcv||ohlcv.length<30) return null;

const lows=ohlcv.map(d=>d[3]);
const closes=ohlcv.map(d=>d[4]);

const rsiValues=RSI.calculate({values:closes,period:14});
if(rsiValues.length<15) return null;

const lastRsi=rsiValues[rsiValues.length-1];

let baseStrength=0;

if(lastRsi<lowerBound)
baseStrength=40+(lowerBound-lastRsi)*2;

return{
symbol,
currentPrice:closes[closes.length-1],
strength:Math.min(69,baseStrength),
interval,
isMatch:false
};

}catch(e){return null;}

};

const allResults=[];

for(const interval of intervals){

const tasks=symbols.map(s=>limit(()=>analyzeSymbolRSI(s,interval)));
const results=await Promise.all(tasks);

allResults.push(...results.filter(Boolean));

}

symbols.forEach(s=>{
resultsMap.set(s.symbol,{
symbol:s.symbol,
currentPrice:s.currentPrice,
strength:0,
intervals:[],
matches:[]
});
});

allResults.forEach(r=>{
const ex=resultsMap.get(r.symbol);
if(ex){
ex.intervals.push(r.interval);
ex.strength=Math.max(ex.strength,r.strength);
}
});

const finalResults=Array.from(resultsMap.values())
.sort((a,b)=>b.strength-a.strength);

await saveResults(finalResults,RSI_DATA_FILE);

res.json(finalResults);

}catch(e){
res.status(500).json({error:e.message});
}

});

/* -------------------------------------------------------
   MACD ANALYSIS
--------------------------------------------------------*/

app.get('/analyze',async(req,res)=>{

const settings=await loadSettings();
const intervals=(req.query.intervals||settings.intervals.join(',')).split(',');
const analysisType=req.query.type||settings.type;

try{

const tickers=await binance.fetchTickers();

const usdtTickers=Object.values(tickers)
.filter(t=>t.symbol&&t.symbol.endsWith('/USDT'));

const symbols=usdtTickers
.sort((a,b)=>(b.quoteVolume||0)-(a.quoteVolume||0))
.slice(0,50)
.map(formatTicker);

const resultsMap=new Map();

const analyzeSymbol=async(coinData,interval)=>{

const {symbol}=coinData;
const ccxtSymbol=`${symbol}USDT`;

try{

const ohlcv=await getOHLCV(ccxtSymbol,interval);
if(!ohlcv||ohlcv.length<30) return null;

const closes=ohlcv.map(d=>d[4]);

const macd=MACD.calculate({
values:closes,
fastPeriod:12,
slowPeriod:26,
signalPeriod:9
});

if(macd.length<20) return null;

const last=macd[macd.length-1];
const prev=macd[macd.length-2];

let strength=0;

if(last.histogram>prev.histogram && last.histogram<0)
strength=40;

return{
symbol,
currentPrice:closes[closes.length-1],
strength,
interval,
isMatch:false
};

}catch(e){return null;}

};

const allResults=[];

for(const interval of intervals){

const tasks=symbols.map(s=>limit(()=>analyzeSymbol(s,interval)));
const results=await Promise.all(tasks);

allResults.push(...results.filter(Boolean));

}

symbols.forEach(s=>{
resultsMap.set(s.symbol,{
symbol:s.symbol,
currentPrice:s.currentPrice,
strength:0,
intervals:[],
matches:[]
});
});

allResults.forEach(r=>{
const ex=resultsMap.get(r.symbol);
if(ex){
ex.intervals.push(r.interval);
ex.strength=Math.max(ex.strength,r.strength);
}
});

const finalResults=Array.from(resultsMap.values())
.sort((a,b)=>b.strength-a.strength);

await saveResults(finalResults);

res.json(finalResults);

}catch(e){
res.status(500).json({error:e.message});
}

});

/* -------------------------------------------------------
   ARBITRAGE
--------------------------------------------------------*/

const ARB_EXCHANGES=[
'binance','bybit','okx','kucoin','gateio',
'mexc','bitget','kraken','bitfinex','coinbase',
'poloniex','hitbtc','coinex','ascendex','phemex',
'toobit','deepcoin','htx','huobi','whitebit','xt'
];

const arbExchangeInstances={};

function getArbExchange(id){
if(!arbExchangeInstances[id]){
try{
arbExchangeInstances[id]=new ccxt[id]({enableRateLimit:true,timeout:10000});
}catch(e){return null;}
}
return arbExchangeInstances[id];
}

app.get('/api/arbitrage-last-results',async(req,res)=>{
res.json(await loadResults(ARB_DATA_FILE));
});

app.get('/api/arbitrage',async(req,res)=>{

try{

const fetchTasks=ARB_EXCHANGES.map(id=>(async()=>{
const ex=getArbExchange(id);
if(!ex) return [];

try{

const tickers=await ex.fetchTickers();

return Object.values(tickers)
.filter(t=>t.symbol&&t.symbol.endsWith('/USDT')&&t.bid>0&&t.ask>0)
.map(t=>({
exchange:id.toUpperCase(),
symbol:t.symbol,
bid:t.bid,
ask:t.ask,
bidVolume:t.bidVolume,
askVolume:t.askVolume
}));

}catch(e){return[];}

})());

const allResults=await Promise.all(fetchTasks);
const allTickers=allResults.flat();

const groups={};

allTickers.forEach(t=>{
if(!groups[t.symbol]) groups[t.symbol]=[];
groups[t.symbol].push(t);
});

const opportunities=[];

for(const [symbol,tickers] of Object.entries(groups)){

if(tickers.length<2) continue;

let minAsk=tickers[0];
let maxBid=tickers[0];

tickers.forEach(t=>{
if(t.ask<minAsk.ask) minAsk=t;
if(t.bid>maxBid.bid) maxBid=t;
});

const diff=((maxBid.bid-minAsk.ask)/minAsk.ask*100);

if(diff>=0.1&&diff<5){

opportunities.push({
symbol,
maxDiff:diff.toFixed(2),
liquidityScore:Math.min(minAsk.askVolume||0,maxBid.bidVolume||0),
prices:tickers
});

}

}

const result={
timestamp:new Date().toISOString(),
opportunities:opportunities.sort((a,b)=>b.maxDiff-a.maxDiff)
};

await saveResults(result,ARB_DATA_FILE);

res.json(result);

}catch(e){
res.status(500).json({error:e.message});
}

});

/* -------------------------------------------------------
   SERVER START
--------------------------------------------------------*/

(async()=>{
await binance.loadMarkets();

app.listen(port,'0.0.0.0',()=>{
console.log(`Server running at http://0.0.0.0:${port}`);
});

})();
