const http = require('http');
const https = require('https');
const url = require('url');

const PORT = 8081;

// ECOS API 키
const ECOS_KEY = 'RVE8ZH17L6IACFDWVCH6';
// KOSIS API 키
const KOSIS_KEY = 'MzNiMDRhOTQ4ZGYxYjVjY2RhYTE2MGZjZDIwMjgzNWE=';
// 공공데이터포털 키
const DATA_KEY = 'ae6660f3eef09e7224e6f9a37fd085b31c9b837e231bf048337a9664c1f2c52b';

const CORS_HEADERS = {
  'Access-Control-Allow-Origin': '*',
  'Access-Control-Allow-Methods': 'GET, POST, OPTIONS',
  'Access-Control-Allow-Headers': 'Content-Type',
  'Content-Type': 'application/json'
};

function fetchUrl(targetUrl) {
  return new Promise((resolve, reject) => {
    https.get(targetUrl, (res) => {
      let data = '';
      res.on('data', chunk => data += chunk);
      res.on('end', () => resolve(data));
    }).on('error', reject);
  });
}

function getDateRange() {
  const now = new Date();
  const end = now.toISOString().slice(0,10).replace(/-/g,'');
  const start = new Date(now - 30*86400000).toISOString().slice(0,10).replace(/-/g,'');
  return { start, end };
}

const server = http.createServer(async (req, res) => {
  // CORS preflight
  if (req.method === 'OPTIONS') {
    res.writeHead(200, CORS_HEADERS);
    res.end();
    return;
  }

  const parsed = url.parse(req.url, true);
  const path = parsed.pathname;

  try {
    // ── ECOS 기준금리
    if (path === '/ecos/rate') {
      const { start, end } = getDateRange();
      const u = `https://ecos.bok.or.kr/api/StatisticSearch/${ECOS_KEY}/json/kr/1/5/722Y001/D/${start}/${end}/0101000`;
      const data = await fetchUrl(u);
      res.writeHead(200, CORS_HEADERS);
      res.end(data);
    }
    // ── ECOS 원/달러
    else if (path === '/ecos/usd') {
      const { start, end } = getDateRange();
      const u = `https://ecos.bok.or.kr/api/StatisticSearch/${ECOS_KEY}/json/kr/1/5/731Y001/D/${start}/${end}/0000001`;
      const data = await fetchUrl(u);
      res.writeHead(200, CORS_HEADERS);
      res.end(data);
    }
    // ── ECOS 국고채 3년
    else if (path === '/ecos/bond3') {
      const { start, end } = getDateRange();
      const u = `https://ecos.bok.or.kr/api/StatisticSearch/${ECOS_KEY}/json/kr/1/5/817Y002/D/${start}/${end}/010200000`;
      const data = await fetchUrl(u);
      res.writeHead(200, CORS_HEADERS);
      res.end(data);
    }
    // ── ECOS 국고채 10년
    else if (path === '/ecos/bond10') {
      const { start, end } = getDateRange();
      const u = `https://ecos.bok.or.kr/api/StatisticSearch/${ECOS_KEY}/json/kr/1/5/817Y002/D/${start}/${end}/010210000`;
      const data = await fetchUrl(u);
      res.writeHead(200, CORS_HEADERS);
      res.end(data);
    }
    // ── KRX 금시세
    else if (path === '/gold') {
      const { start, end } = getDateRange();
      const u = `https://apis.data.go.kr/1160100/service/GetGeneralProductInfoService/getGoldPriceInfo?serviceKey=${DATA_KEY}&resultType=json&beginBasDt=${start}&endBasDt=${end}&numOfRows=5&pageNo=1`;
      const data = await fetchUrl(u);
      res.writeHead(200, CORS_HEADERS);
      res.end(data);
    }
    // ── KOSIS 인구추계
    else if (path === '/kosis/pop') {
      const u = `https://kosis.kr/openapi/Param/statisticsParameterData.do?method=getList&apiKey=${KOSIS_KEY}&orgId=101&tblId=DT_1BPA401&objL1=ALL&objL2=ALL&itmId=T10&prdSe=Y&startPrdDe=2024&endPrdDe=2026&format=json&jsonVD=Y`;
      const data = await fetchUrl(u);
      res.writeHead(200, CORS_HEADERS);
      res.end(data);
    }
    // ── Claude API 프록시
    else if (path === '/claude') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        try {
          const payload = JSON.parse(body);
          const ANTHROPIC_KEY = payload._key || '';
          delete payload._key;

          const postData = JSON.stringify(payload);
          const options = {
            hostname: 'api.anthropic.com',
            path: '/v1/messages',
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-api-key': ANTHROPIC_KEY,
              'anthropic-version': '2023-06-01',
              'Content-Length': Buffer.byteLength(postData)
            }
          };

          const apiReq = https.request(options, (apiRes) => {
            let data = '';
            apiRes.on('data', chunk => data += chunk);
            apiRes.on('end', () => {
              res.writeHead(200, CORS_HEADERS);
              res.end(data);
            });
          });
          apiReq.on('error', (e) => {
            res.writeHead(500, CORS_HEADERS);
            res.end(JSON.stringify({ error: e.message }));
          });
          apiReq.write(postData);
          apiReq.end();
        } catch(e) {
          res.writeHead(500, CORS_HEADERS);
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }
    // ── Claude API 프록시
    else if (path === '/claude') {
      let body = '';
      req.on('data', chunk => body += chunk);
      req.on('end', async () => {
        try {
          const payload = JSON.parse(body);
          const ANTHROPIC_KEY = payload._key || '';
          delete payload._key;
          const postData = JSON.stringify(payload);
          const options = {
            hostname: 'api.anthropic.com',
            path: '/v1/messages',
            method: 'POST',
            headers: {
              'Content-Type': 'application/json',
              'x-api-key': ANTHROPIC_KEY,
              'anthropic-version': '2023-06-01',
              'Content-Length': Buffer.byteLength(postData)
            }
          };
          const apiReq = https.request(options, (apiRes) => {
            let data = '';
            apiRes.on('data', chunk => data += chunk);
            apiRes.on('end', () => { res.writeHead(200, CORS_HEADERS); res.end(data); });
          });
          apiReq.on('error', (e) => { res.writeHead(500, CORS_HEADERS); res.end(JSON.stringify({error: e.message})); });
          apiReq.write(postData);
          apiReq.end();
        } catch(e) {
          res.writeHead(500, CORS_HEADERS);
          res.end(JSON.stringify({ error: e.message }));
        }
      });
      return;
    }
    else {
      res.writeHead(404, CORS_HEADERS);
      res.end(JSON.stringify({ error: 'Not found' }));
    }
  } catch (e) {
    res.writeHead(500, CORS_HEADERS);
    res.end(JSON.stringify({ error: e.message }));
  }
});

server.listen(PORT, () => {
  console.log(`\n✅ 브리핑 데스크 프록시 서버 실행 중`);
  console.log(`   포트: ${PORT}`);
  console.log(`   ECOS:  http://localhost:${PORT}/ecos/rate`);
  console.log(`   KRX:   http://localhost:${PORT}/gold`);
  console.log(`   KOSIS: http://localhost:${PORT}/kosis/pop`);
  console.log(`\n   briefing_v3.html 은 http://localhost:8080 으로 접속\n`);
});
