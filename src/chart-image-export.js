export async function exportChartPng({chart,container,caption,filename}){
 if(!chart||!container)throw new Error('图表尚未就绪');
 const base=chart.takeScreenshot(false,false),scaleX=base.width/container.clientWidth,scaleY=base.height/container.clientHeight;
 if(!base.width||!base.height||!Number.isFinite(scaleX)||!Number.isFinite(scaleY))throw new Error('图表尺寸无效');
 const canvas=document.createElement('canvas'),footer=Math.ceil(28*scaleY);canvas.width=base.width;canvas.height=base.height+footer;
 const context=canvas.getContext('2d');if(!context)throw new Error('当前浏览器无法导出图片');
 context.fillStyle='#ffffff';context.fillRect(0,0,canvas.width,canvas.height);context.drawImage(base,0,0);
 const layer=container.querySelector('.tv-anchor-layer');
 if(layer){const svg=layer.cloneNode(true);svg.querySelectorAll('.tv-drawing-handle').forEach(node=>node.remove());svg.setAttribute('xmlns','http://www.w3.org/2000/svg');const url=URL.createObjectURL(new Blob([new XMLSerializer().serializeToString(svg)],{type:'image/svg+xml;charset=utf-8'}));
  try{const picture=new Image();await new Promise((resolve,reject)=>{const timer=setTimeout(()=>reject(new Error('绘图图层导出超时')),10000);picture.onload=()=>{clearTimeout(timer);resolve();};picture.onerror=()=>{clearTimeout(timer);reject(new Error('绘图图层导出失败'));};picture.src=url;});context.drawImage(picture,0,0,Number(svg.getAttribute('width'))*scaleX,Number(svg.getAttribute('height'))*scaleY);}finally{URL.revokeObjectURL(url);}}
 context.fillStyle='#64748b';context.font=`${Math.max(10,Math.round(10*scaleY))}px sans-serif`;context.fillText(caption,Math.round(8*scaleX),base.height+Math.round(17*scaleY),canvas.width-Math.round(16*scaleX));
 const blob=await new Promise(resolve=>canvas.toBlob(resolve,'image/png'));if(!blob)throw new Error('PNG生成失败');
 const url=URL.createObjectURL(blob),anchor=document.createElement('a');anchor.href=url;anchor.download=filename;anchor.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 return {width:canvas.width,height:canvas.height,bytes:blob.size};
}
