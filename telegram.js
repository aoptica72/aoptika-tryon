/* Browser-only photo try-on. Only the approved DACCHi photograph is used as source. */
const $ = id => document.getElementById(id);
const preview = $('preview'), ctx = preview.getContext('2d');
const $status = $('status');
const state = {models: [], model: null, photo: null, overlay: null, anchor: {x:.5,y:.43,eyeDist:0,angle:0}, auto: null, drag: null, serial:0, showOriginal:false};
const tg = window.Telegram?.WebApp;
tg?.ready(); tg?.expand();
function status(text){$status.textContent=text;}
const clamp = (x,min,max) => Math.max(min,Math.min(max,x));
const ownImage = path => new Promise((resolve,reject)=>{const image=new Image();image.onload=()=>resolve(image);image.onerror=()=>reject(new Error('Не удалось загрузить '+path));image.src=path;});

async function prepareCutout(photo,mask){
  if(photo.naturalWidth!==mask.source_width || photo.naturalHeight!==mask.source_height) throw new Error('Размер утверждённого изображения изменился. Проверьте версию маски.');
  const width=photo.naturalWidth,height=photo.naturalHeight;
  const base=document.createElement('canvas');base.width=width;base.height=height;
  const b=base.getContext('2d',{willReadFrequently:true});b.drawImage(photo,0,0);
  const selected=document.createElement('canvas');selected.width=width;selected.height=height;
  const m=selected.getContext('2d',{willReadFrequently:true});
  m.fillStyle='white';
  const polygon=(points,fill)=>{m.fillStyle=fill;m.beginPath();m.moveTo(points[0][0],points[0][1]);for(const p of points.slice(1))m.lineTo(p[0],p[1]);m.closePath();m.fill();};
  for(const p of mask.outer)polygon(p,'white');
  polygon(mask.bridge,'white');
  for(const p of mask.holes)polygon(p,'black');
  const pixels=b.getImageData(0,0,width,height),a=pixels.data;
  const selection=m.getImageData(0,0,width,height).data;
  let left=width,top=height,right=0,bottom=0;
  for(let y=0;y<height;y++)for(let x=0;x<width;x++){
    const i=(y*width+x)*4;
    // Remove white background and the white backing photographed behind semi-transparent frames.
    const lum=.299*a[i]+.587*a[i+1]+.114*a[i+2];
    const alpha=Math.round(clamp((255-lum)*2.1,0,255)*selection[i]/255);
    a[i+3]=alpha;
    if(alpha>3){left=Math.min(left,x);right=Math.max(right,x);top=Math.min(top,y);bottom=Math.max(bottom,y);}
  }
  if(left>right)throw new Error('Не удалось отделить фронт оправы от фона.');
  b.putImageData(pixels,0,0);
  const crop=document.createElement('canvas');crop.width=right-left+1;crop.height=bottom-top+1;
  crop.getContext('2d').drawImage(base,left,top,crop.width,crop.height,0,0,crop.width,crop.height);
  return crop;
}

function landmarkAnchor(pts){
  if(!pts?.[33] || !pts?.[263]) return null;
  const l=pts[33],r=pts[263];
  const dx=(r.x-l.x)*preview.width,dy=(r.y-l.y)*preview.height;
  const dist=Math.hypot(dx,dy);
  if(dist<Math.min(preview.width,preview.height)*.04)return null;
  return {x:(l.x+r.x)/2,y:(l.y+r.y)/2,eyeDist:dist,angle:Math.atan2(dy,dx)};
}
let detectorPromise;
async function detectFace(image){
  if(!detectorPromise){
    detectorPromise=(async()=>{
      const {FaceLandmarker,FilesetResolver}=await import('./vision_bundle.mjs');
      const resolver=await FilesetResolver.forVisionTasks(new URL('./',location.href).href);
      return FaceLandmarker.createFromOptions(resolver,{baseOptions:{modelAssetPath:new URL('./face_landmarker.task',location.href).href,delegate:'CPU'},runningMode:'IMAGE',numFaces:1});
    })().catch(e=>{detectorPromise=undefined;throw e});
  }
  const detector=await detectorPromise;
  return detector.detect(image).faceLandmarks?.[0]||null;
}
function resetControls(){for(const id of ['horizontal','vertical','angle'])$(id).value=0;$('scale').value=100;$('scale-label').value='100%';$('angle-label').value='0°';state.showOriginal=false;$('compare').textContent='До / после';$('compare').setAttribute('aria-pressed','false');}
function draw(){
  if(!state.photo)return;
  ctx.clearRect(0,0,preview.width,preview.height);
  ctx.drawImage(state.photo,0,0,preview.width,preview.height);
  if(state.showOriginal||!state.overlay)return;
  const model=state.model;
  const scaledWidth=(state.anchor.eyeDist ? state.anchor.eyeDist*model.width_to_eye_distance : preview.width*.40)*Number($('scale').value)/100;
  const h=scaledWidth*state.overlay.height/state.overlay.width;
  const x=state.anchor.x*preview.width+Number($('horizontal').value)*preview.width/1000;
  const y=state.anchor.y*preview.height+scaledWidth*model.eye_line_offset_ratio+Number($('vertical').value)*preview.height/1000;
  ctx.save();ctx.translate(x,y);ctx.rotate(state.anchor.angle+Number($('angle').value)*Math.PI/180);
  ctx.drawImage(state.overlay,-scaledWidth/2,-h/2,scaledWidth,h);ctx.restore();
}
async function onPhoto(file){
  if(!file)return;
  if(!$('consent').checked){status('Перед загрузкой отметьте согласие на локальную обработку фото.');return;}
  if(!['image/jpeg','image/png','image/webp'].includes(file.type)){status('Поддерживаются JPG, PNG и WEBP.');return;}
  if(file.size>8*1024*1024){status('Фото слишком большое. Ограничение — 8 МБ.');return;}
  const serial=++state.serial,url=URL.createObjectURL(file);
  try{
    status('Загружаем селфи…');
    const photo=await ownImage(url);
    if(serial!==state.serial)return;
    if(Math.min(photo.naturalWidth,photo.naturalHeight)<160)throw new Error('Фото должно быть не меньше 160 пикселей по каждой стороне.');
    const factor=Math.min(1,1600/Math.max(photo.naturalWidth,photo.naturalHeight));
    preview.width=Math.round(photo.naturalWidth*factor);preview.height=Math.round(photo.naturalHeight*factor);
    state.photo=photo;state.anchor={x:.5,y:.43,eyeDist:0,angle:0};state.auto=null;
    resetControls();preview.hidden=false;$('placeholder').hidden=true;draw();
    status('Фото загружено. Распознаём положение глаз…');
    try{
      const landmarks=await detectFace(photo);
      if(serial!==state.serial)return;
      const anchor=landmarkAnchor(landmarks);
      if(anchor){state.auto={...anchor};state.anchor={...anchor};status('Лицо найдено. Оправа автоматически размещена. При необходимости поправьте её.');}
      else status('Лицо не распознано. Вы можете установить оправу вручную.');
      draw();
    }catch(e){if(serial!==state.serial)return;console.warn('Face detector unavailable',e);status('Распознавание недоступно. Переместите оправу вручную.');}
  }catch(e){if(serial===state.serial)status(e.message||'Не удалось загрузить фото.');}
  finally{URL.revokeObjectURL(url);$('file').value='';$('camera').value='';}
}
for(const id of ['file','camera'])$(id).addEventListener('change',e=>onPhoto(e.target.files?.[0]));
for(const id of ['scale','horizontal','vertical','angle'])$(id).addEventListener('input',()=>{ $('scale-label').value=$('scale').value+'%';$('angle-label').value=$('angle').value+'°';state.showOriginal=false;draw();});
$('reset').addEventListener('click',()=>{if(!state.photo)return;state.anchor={...(state.auto||{x:.5,y:.43,eyeDist:0,angle:0})};resetControls();draw();status('Положение оправы сброшено.');});
$('compare').addEventListener('click',()=>{
  if(!state.photo || !state.overlay){status('Для сравнения сначала загрузите фото.');return;}
  state.showOriginal=!state.showOriginal;
  $('compare').textContent=state.showOriginal?'Показать примерку':'До / после';
  $('compare').setAttribute('aria-pressed',String(state.showOriginal));
  draw();
});
preview.addEventListener('pointerdown',e=>{if(!state.photo)return;state.drag={x:e.clientX,y:e.clientY,ax:state.anchor.x,ay:state.anchor.y};preview.setPointerCapture(e.pointerId);});
preview.addEventListener('pointermove',e=>{if(!state.drag)return;const rect=preview.getBoundingClientRect();state.anchor.x=state.drag.ax+(e.clientX-state.drag.x)/rect.width;state.anchor.y=state.drag.ay+(e.clientY-state.drag.y)/rect.height;state.showOriginal=false;draw();});
for(const ev of ['pointerup','pointercancel','lostpointercapture'])preview.addEventListener(ev,()=>{state.drag=null;});
function download(canvas,name){canvas.toBlob(blob=>{if(!blob){status('Не удалось сохранить PNG.');return;}const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download=name;document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1500);},'image/png');}
$('save').addEventListener('click',()=>{if(!state.photo || !state.overlay){status('Сначала загрузите фото и дождитесь загрузки оправы.');return;}state.showOriginal=false;$('compare').textContent='До / после';$('compare').setAttribute('aria-pressed','false');draw();download(preview,'a-optika-dacchi-34355-primerka.png');});
$('download-frame').addEventListener('click',()=>{if(!state.overlay){status('Оправа пока не загружена.');return;}download(state.overlay,'dacchi-34355-transparent.png');});
document.querySelectorAll('[data-action]').forEach(button=>button.addEventListener('click',()=>{
  if(!state.model)return;
  const data=JSON.stringify({action:button.dataset.action,sku:state.model.sku});
  if(typeof tg?.sendData==='function' && tg.initData){tg.sendData(data);return;}
  if(button.dataset.action==='favorite'){
    try{localStorage.setItem('aoptika.favorite',state.model.sku);status('Оправа добавлена в избранное на этом устройстве.');}catch{status('Избранное недоступно в этом браузере.');}
    return;
  }
  status('Для заявки откройте примерочную через кнопку Telegram-бота. Контакты салонов: aoptica.ru');
}));

async function init(){
  try{
    const [catalogResponse,maskResponse]=await Promise.all([fetch('./telegram_bot/catalog.json'),fetch('./telegram_bot/mask.json')]);
    if(!catalogResponse.ok || !maskResponse.ok)throw new Error('Каталог не загружен.');
    state.models=await catalogResponse.json();const mask=await maskResponse.json();
    state.model=state.models.find(m=>m.sku==='DACCHI-34355');if(!state.model)throw new Error('DACCHi 34355 отсутствует в каталоге');
    const original=await ownImage('./'+state.model.photo);
    state.overlay=await prepareCutout(original,mask);
    const catalog=$('catalog');const picture=document.createElement('img');picture.src='./'+state.model.photo;picture.alt='Оригинальная фотография DACCHi 34355';
    const info=document.createElement('div');const title=document.createElement('strong');title.textContent=state.model.name;
    const meta=document.createElement('small');meta.textContent=`Размер ${state.model.size_mm.lens}–${state.model.size_mm.bridge}–${state.model.size_mm.temple} мм · Цена/наличие уточняются`;
    info.append(title,meta);catalog.append(picture,info);
    status('Оправа готова. Загрузите фото лица анфас.');draw();
  }catch(e){console.error(e);status('Ошибка подготовки оправы: '+(e.message||'неизвестно'));}
}
init();