// Local viewer only. No uploads, no history; the current GLB is the source.
const http=require('node:http');
const fs=require('node:fs');
const path=require('node:path');
const root=__dirname;
const model=path.join(root,'modelo_paso','paso_completo.glb');
const mime={'.html':'text/html; charset=utf-8','.js':'text/javascript; charset=utf-8','.glb':'model/gltf-binary','.jfif':'image/jpeg','.json':'application/json; charset=utf-8','.png':'image/png'};
const server=http.createServer((req,res)=>{
  res.setHeader('Cache-Control','no-store');
  try{
    const url=new URL(req.url,'http://localhost');
    if(url.pathname==='/'){res.writeHead(302,{Location:'/modelo_paso/visor.html'});res.end();return;}
    if(url.pathname==='/estado'){
      const s=fs.statSync(model);
      res.writeHead(200,{'Content-Type':mime['.json']});
      res.end(JSON.stringify({key:s.mtimeMs+':'+s.size,file:'paso_completo.glb',size:s.size}));
      return;
    }
    let filePath=url.pathname==='/'?'/modelo_paso/visor.html':decodeURIComponent(url.pathname);
    const target=path.resolve(root,'.'+filePath);
    if(!target.startsWith(root+path.sep)){res.writeHead(403);res.end();return;}
    if(!fs.statSync(target).isFile()){res.writeHead(404);res.end();return;}
    res.writeHead(200,{'Content-Type':mime[path.extname(target)]||'application/octet-stream'});
    fs.createReadStream(target).pipe(res);
  }catch(e){res.writeHead(e.code==='ENOENT'?404:500);res.end('Archivo no disponible');}
});
server.listen(8765,'127.0.0.1',()=>console.log('Visor: http://127.0.0.1:8765/ · fuente: modelo_paso/paso_completo.glb'));
server.on('error',e=>{console.error(e.message);process.exitCode=1;});
