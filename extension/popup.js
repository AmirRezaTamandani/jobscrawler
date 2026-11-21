const $ = id => document.getElementById(id);
let jobs = [], checks = [], stopped = false, originTab;
let working = false;
function setBusy(button, active, label) {
 if (active) button.dataset.idleLabel = button.textContent;
 button.disabled = active;
 button.classList.toggle('is-loading', active);
 button.setAttribute('aria-busy', String(active));
 button.textContent = active ? label : button.dataset.idleLabel;
}
chrome.tabs.query({active:true,currentWindow:true}).then(tabs => { originTab = tabs[0]?.id; });
const label = {jobinja:'جابینجا',jobvision:'جاب‌ویژن'};
const BATCH_SIZE = 100;
function safeJob(j) {
  try {
    const u = new URL(j.url);
    const host = {jobinja:'jobinja.ir',jobvision:'jobvision.ir'}[j.source];
    if (!host || u.protocol !== 'https:' || u.hostname !== host || u.username || u.password || u.port || !j.source_id || !j.title) return null;
    const path = j.source === 'jobinja' ? u.pathname.match(/^\/companies\/[^/]+\/jobs\/([a-z0-9_-]+)(?:\/[^/]*)?\/?$/i) : u.pathname.match(/^\/jobs\/(\d+)\/?$/);
    return path && path[1] === String(j.source_id) ? {source:j.source,source_id:String(j.source_id),title:String(j.title),company:String(j.company || ''),url:u.href} : null;
  } catch { return null; }
}
function inspectPage(source, action, resume, expected, expectedId) {
  const path = source === 'jobinja' ? location.pathname.match(/^\/companies\/[^/]+\/jobs\/([a-z0-9_-]+)(?:\/[^/]*)?\/?$/i) : location.pathname.match(/^\/jobs\/(\d+)(?:\/[^/]*)?\/?$/);
  if (!path || path[1] !== expectedId) return {state:'unknown',message:'نشانی آگهی تغییر کرده است'};
  const text = document.body?.innerText || '';
  if (/captcha|کپچا|کد امنیتی|ربات نیستید/i.test(text)) return {state:'blocked',message:'نیاز به بررسی امنیتی'};
  if (source === 'jobinja') {
    if (document.querySelector('.application-innerCard')) return {state:'already', message:'قبلاً درخواست ثبت شده'};
    const form = document.querySelector('form.apply-form');
    const profile = document.querySelector('#apply_choice_jobinja_profile');
    const uploaded = document.querySelector('#apply_choice_uploaded_cv');
    const button = form?.querySelector('input[type=submit],button[type=submit]');
    const choice = resume === 'uploaded' ? uploaded : profile;
    if (!form || !button || !choice || choice.disabled) return {state:'unknown',message:'فرم یا رزومه انتخاب‌شده در دسترس نیست'};
    const account = form.innerText.replace(/\s+/g,' ').slice(0,300);
    if (!account || !account.includes('رزومه')) return {state:'unknown',message:'حساب یا رزومه قابل تشخیص نیست'};
    if (action === 'submit') { if (account !== expected) return {state:'unknown',message:'حساب یا رزومه پس از بررسی تغییر کرده است'}; choice.click(); button.click(); }
    return {state: action === 'submit' ? 'submitted' : 'ready', message:account};
  }
  const profile = document.querySelector('a[href="/my-cv"]');
  const details = profile?.parentElement;
  const section = details?.parentElement;
  const values = [...(details?.querySelectorAll('p') || [])].map(p => p.innerText.trim()).filter(Boolean);
  const button = section?.querySelector('.send-resume button.jvt-btn-send-resume');
  if (!button || values.length < 2) return {state:'unknown', message:'حساب یا فرم رزومه قابل تشخیص نیست'};
  const account = `حساب: ${values[0]} | رزومه: ${values[1]}`;
  if (action === 'submit') { if (account.slice(0,300) !== expected) return {state:'unknown',message:'حساب یا رزومه پس از بررسی تغییر کرده است'}; button.click(); }
  return {state:action === 'submit' ? 'submitted' : 'ready',message:account.slice(0,300)};
}
function inspectSession(source) {
 const text = document.body?.innerText || '';
 if (/captcha|کپچا|کد امنیتی|ربات نیستید/i.test(text)) return 'unknown';
 if (source === 'jobinja') {
   if (/رزومه من/.test(text) && /خوش آمدید/.test(text)) return 'logged_in';
   if (/ورود کارجو|ورود به حساب/.test(text) && !/خوش آمدید/.test(text)) return 'logged_out';
 } else {
   if (document.querySelector('a[href*="/my-cv"]')) return 'logged_in';
   if (/ورود کارجو|ورود به حساب/.test(text) && !document.querySelector('a[href*="/my-cv"]')) return 'logged_out';
 }
 return 'unknown';
}
async function withTab(url, fn, args) {
 const tab = await chrome.tabs.create({url,active:false});
 try {
   await new Promise((resolve,reject) => {
     let timer = setTimeout(() => {chrome.tabs.onUpdated.removeListener(listener);reject(new Error('زمان دریافت صفحه تمام شد'));},30000);
     function listener(id, change) {if(id === tab.id && change.status === 'complete'){clearTimeout(timer);chrome.tabs.onUpdated.removeListener(listener);resolve();}}
     chrome.tabs.onUpdated.addListener(listener);
     chrome.tabs.get(tab.id).then(t => {if(t.status === 'complete'){clearTimeout(timer);chrome.tabs.onUpdated.removeListener(listener);resolve();}}).catch(reject);
   });
   await new Promise(r => setTimeout(r,2500));
   const result = await chrome.scripting.executeScript({target:{tabId:tab.id},func:fn,args});
   if (args[1] === 'submit' && result[0]?.result?.state === 'submitted') await new Promise(r => setTimeout(r,5000));
   return result[0]?.result;
 } finally { await chrome.tabs.remove(tab.id).catch(()=>{}); }
}
function render() {
 $('items').replaceChildren(...jobs.map((job,i) => {
   const li=document.createElement('li'), title=document.createElement('strong'), detail=document.createElement('div');
   title.textContent=job.title+' | '+job.company+' | '+label[job.source];
   detail.textContent=checks[i]?.message || 'در انتظار بررسی';
   detail.className=checks[i]?.state === 'ready' ? 'ok':'error';
   li.append(title,detail);return li;
 }));
 $('start').disabled=working || !checks.some(c=>c?.state==='ready');
}
$('review').onclick = async () => {
 try {
  const data=JSON.parse($('batch').value);
  if(data.version!==1 || !Array.isArray(data.jobs) || !data.jobs.length) throw Error('فهرست باید حداقل یک فرصت داشته باشد.');
  const parsed=data.jobs.map(safeJob);if(parsed.some(x=>!x)) throw Error('آدرس یا اطلاعات یکی از فرصت‌ها معتبر نیست.');
  jobs=[...new Map(parsed.map(j=>[j.source+':'+j.source_id,j])).values()];checks=[];$('review-area').hidden=false;working=true;setBusy($('review'),true,'در حال بررسی…');$('resume').disabled=true;$('start').disabled=true;render();
  for (let i=0;i<jobs.length;i++) {
   $('status').textContent=`در حال بررسی ${i+1} از ${jobs.length}، دستهٔ ${Math.floor(i/BATCH_SIZE)+1} از ${Math.ceil(jobs.length/BATCH_SIZE)}`;
   try { checks[i]=await withTab(jobs[i].url,inspectPage,[jobs[i].source,'review',$('resume').value,undefined,jobs[i].source_id]); }
   catch(e){checks[i]={state:'unknown',message:'دریافت یا بررسی فرم ممکن نشد'};}
   render();
  }
  $('status').textContent='بررسی تمام شد. حساب و رزومه را پیش از ارسال بخوانید.';
 } catch(e) { $('status').textContent='فهرست معتبر نیست. '+e.message; }
 finally { if(working){working=false;setBusy($('review'),false);$('resume').disabled=false;render();} }
};
$('resume').onchange=()=>{checks=[];render();$('status').textContent='برای بررسی رزومه جدید دوباره فهرست را بررسی کنید.';};
$('sessions').onclick=async()=>{
 setBusy($('sessions'),true,'در حال بررسی حساب‌ها…'); const result={};
 for(const [source,url] of Object.entries({jobinja:'https://jobinja.ir/',jobvision:'https://jobvision.ir/'})) {
  try { result[source]=await withTab(url,inspectSession,[source]) || 'unknown'; } catch { result[source]='unknown'; }
 }
 const names={logged_in:'وارد شده',logged_out:'وارد نشده',unknown:'نامشخص'};
 $('session-results').textContent=Object.entries(result).map(([s,v])=>label[s]+': '+names[v]).join(' | ');
 try { if(originTab) await chrome.scripting.executeScript({target:{tabId:originTab},world:'MAIN',func:(detail)=>window.dispatchEvent(new CustomEvent('felowin-session-status',{detail})),args:[{...result,checkedAt:new Date().toISOString()}]}); } catch {}
 setBusy($('sessions'),false);
};
$('start').onclick=async()=>{
 if (!confirm('درخواست‌های آماده با حساب و رزومه نمایش‌داده‌شده به کارفرماها ارسال می‌شوند. ادامه می‌دهید؟')) return;
 working=true;setBusy($('start'),true,'در حال ارسال…');$('review').disabled=true;$('resume').disabled=true;$('stop').hidden=false;stopped=false;
 const {attempted={}}=await chrome.storage.local.get('attempted');
 for(let batchStart=0;batchStart<jobs.length&&!stopped;batchStart+=BATCH_SIZE) {
  const batchEnd=Math.min(batchStart+BATCH_SIZE,jobs.length);
  for(let i=batchStart;i<batchEnd&&!stopped;i++) {
  const job=jobs[i], key=job.source+':'+job.source_id;
  if(checks[i]?.state!=='ready') continue;
  if(attempted[key]){checks[i]={state:'unknown',message:'پیش‌تر تلاش شده؛ وضعیت را در سایت بررسی کنید.'};render();continue;}
  $('status').textContent=`در حال ارسال ${i+1} از ${jobs.length}، دستهٔ ${Math.floor(batchStart/BATCH_SIZE)+1} از ${Math.ceil(jobs.length/BATCH_SIZE)}`;
  try {
   attempted[key]={at:new Date().toISOString(),state:'uncertain'};await chrome.storage.local.set({attempted});
   const sent=await withTab(job.url,inspectPage,[job.source,'submit',$('resume').value,checks[i].message,job.source_id]);
   if(sent?.state!=='submitted') { checks[i]=sent || {state:'unknown',message:'فرم تغییر کرده است'};stopped=true; }
   else if(job.source==='jobinja') {
    const verified=await withTab(job.url,inspectPage,[job.source,'verify',$('resume').value,undefined,job.source_id]);
    if(verified?.state==='already'){attempted[key].state='success';await chrome.storage.local.set({attempted});checks[i]={state:'success',message:'درخواست در جابینجا ثبت شد.'};}
    else {checks[i]={state:'unknown',message:'تأیید دریافت نشد؛ وضعیت را در جابینجا بررسی کنید.'};stopped=true;}
   } else {checks[i]={state:'unknown',message:'دکمه ارسال انتخاب شد. نتیجه را در جاب‌ویژن بررسی کنید.'};stopped=true;}
  } catch { checks[i]={state:'unknown',message:'نتیجه نامشخص است؛ پیش از تلاش دوباره سایت را بررسی کنید.'};stopped=true; }
  render();
  }
 }
 $('status').textContent=stopped?'ارسال متوقف شد. وضعیت فرصت مشخص‌شده را در سایت بررسی کنید.':'پردازش فهرست تمام شد.';
 $('stop').hidden=true;$('review').disabled=false;$('resume').disabled=false;working=false;setBusy($('start'),false);$('start').disabled=true;
};
$('stop').onclick=()=>{stopped=true;};
