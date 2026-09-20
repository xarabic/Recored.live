import os
import uuid
import threading
import time
from pathlib import Path
from flask import Flask, request, jsonify, send_file, render_template_string
import yt_dlp

app = Flask(__name__)

RECORDINGS_DIR = Path("/tmp/recordings")
RECORDINGS_DIR.mkdir(exist_ok=True, parents=True)

MAX_RECORDING_SECONDS = 2 * 60 * 60
jobs = {}

HTML_PAGE = """
<!DOCTYPE html>
<html lang="ar" dir="rtl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>ستريم كابتشر</title>
<script src="https://cdn.tailwindcss.com"></script>
<link href="https://fonts.googleapis.com/css2?family=Tajawal:wght@400;700;900&display=swap" rel="stylesheet">
<style>
  *{box-sizing:border-box;margin:0;padding:0}
  body{background:#070711;color:#fff;font-family:'Tajawal',system-ui,sans-serif;min-height:100vh;padding:16px}
  .glass{background:rgba(255,255,255,0.05);border:1px solid rgba(255,255,255,0.1);border-radius:18px;padding:20px;margin-bottom:16px}
  .btn{background:linear-gradient(135deg,#ff2e7e,#7a4bff);color:#fff;border:0;padding:16px 24px;border-radius:12px;font-weight:700;font-size:16px;cursor:pointer;font-family:inherit;width:100%}
  .btn:disabled{opacity:0.5;cursor:not-allowed}
  .grad{background:linear-gradient(90deg,#ff2e7e,#7a4bff,#22d3ee);-webkit-background-clip:text;-webkit-text-fill-color:transparent;background-clip:text}
  input{width:100%;padding:16px;border-radius:12px;border:1px solid rgba(255,255,255,0.15);background:rgba(0,0,0,0.4);color:#fff;font-size:16px;font-family:inherit;margin-bottom:12px}
  .status{padding:16px;border-radius:12px;margin-top:16px;font-weight:600;line-height:1.8}
  .status.ok{background:rgba(16,185,129,0.15);border:1px solid rgba(16,185,129,0.4);color:#6ee7b7}
  .status.err{background:rgba(239,68,68,0.15);border:1px solid rgba(239,68,68,0.4);color:#fca5a5}
  .status.info{background:rgba(34,211,238,0.15);border:1px solid rgba(34,211,238,0.4);color:#67e8f9}
  .job{background:rgba(255,255,255,0.03);border:1px solid rgba(255,255,255,0.08);border-radius:14px;padding:16px;margin-bottom:12px}
  .job-title{font-weight:700;margin-bottom:8px;word-break:break-all;font-size:14px}
  .job-meta{font-size:13px;color:#9aa0b5;margin-bottom:12px;line-height:1.7}
  .actions{display:flex;gap:8px;flex-wrap:wrap}
  .actions button,.actions a{padding:10px 16px;border-radius:10px;font-size:13px;font-weight:700;text-decoration:none;border:0;cursor:pointer;font-family:inherit}
  .download{background:linear-gradient(135deg,#10b981,#059669);color:#fff}
  .delete{background:rgba(239,68,68,0.2);color:#fca5a5;border:1px solid rgba(239,68,68,0.4)}
  h1{font-size:26px;text-align:center;margin-bottom:6px;font-weight:900}
  .sub{text-align:center;color:#9aa0b5;margin-bottom:20px;font-size:14px}
  .info-box{background:rgba(34,211,238,0.08);border:1px solid rgba(34,211,238,0.3);border-radius:12px;padding:14px;font-size:13px;color:#a5f3fc;margin-bottom:20px;line-height:1.8}
</style>
</head>
<body>
<div style="max-width:600px;margin:0 auto;padding-top:16px">
  <h1>🎬 ستريم <span class="grad">كابتشر</span></h1>
  <p class="sub">سجل أي بث مباشر بضغطة واحدة</p>
  <div class="info-box">
    ⚡ أول زيارة قد تأخذ 30-60 ثانية.<br>
    ⏱️ الحد الأقصى: ساعتان.<br>
    ⚠️ حمّل التسجيل فوراً.
  </div>
  <div class="glass">
    <input id="url" type="url" placeholder="الصق رابط البث هنا" autocomplete="off">
    <button id="startBtn" class="btn">▶ ابدأ التسجيل</button>
    <div id="status"></div>
  </div>
  <div class="glass">
    <h2 style="margin-bottom:14px;font-size:18px">📁 التسجيلات</h2>
    <div id="jobs"><p style="color:#9aa0b5;font-size:14px">لا توجد تسجيلات بعد.</p></div>
  </div>
</div>
<script>
const $ = s => document.querySelector(s);
let currentJobId = null, pollTimer = null;
function showStatus(msg, type='info'){ $('#status').innerHTML = `<div class="status ${type}">${msg}</div>`; }
function formatTime(sec){ sec=Math.floor(sec||0); return [Math.floor(sec/3600),Math.floor((sec%3600)/60),sec%60].map(n=>String(n).padStart(2,'0')).join(':'); }
function formatSize(b){ if(!b)return '0 B'; if(b<1048576)return (b/1024).toFixed(1)+' KB'; if(b<1073741824)return (b/1048576).toFixed(1)+' MB'; return (b/1073741824).toFixed(2)+' GB'; }
function escapeHtml(s){ return String(s||'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
async function startRecording(){
  const url = $('#url').value.trim();
  if(!url){ showStatus('❌ الرجاء إدخال رابط','err'); return; }
  $('#startBtn').disabled = true;
  showStatus('⏳ جاري البدء...','info');
  try{
    const res = await fetch('/api/record',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url})});
    const data = await res.json();
    if(data.error){ showStatus('❌ '+data.error,'err'); $('#startBtn').disabled=false; return; }
    currentJobId = data.id;
    showStatus('✅ بدأ التسجيل!','ok');
    $('#url').value=''; loadJobs(); startPolling();
  }catch(err){ showStatus('❌ فشل: '+err.message,'err'); $('#startBtn').disabled=false; }
}
function startPolling(){
  if(pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(async () => {
    if(!currentJobId) return;
    try{
      const res = await fetch('/api/status/'+currentJobId);
      const data = await res.json();
      if(data.status==='recording'||data.status==='starting'){
        showStatus(`🔴 يسجّل<br>⏱️ ${formatTime(data.duration)} • 💾 ${formatSize(data.size)}`,'info');
      }else if(data.status==='done'){
        showStatus('✅ اكتمل!','ok'); clearInterval(pollTimer); currentJobId=null; $('#startBtn').disabled=false; loadJobs();
      }else if(data.status==='error'){
        showStatus('❌ '+escapeHtml(data.error||''),'err'); clearInterval(pollTimer); currentJobId=null; $('#startBtn').disabled=false;
      }
    }catch(e){}
  },3000);
}
async function loadJobs(){
  try{
    const res = await fetch('/api/jobs');
    const jobs = await res.json();
    if(jobs.length===0){ $('#jobs').innerHTML='<p style="color:#9aa0b5;font-size:14px">لا توجد تسجيلات.</p>'; return; }
    $('#jobs').innerHTML = jobs.map(j=>`
      <div class="job">
        <div class="job-title">${escapeHtml(j.title||'بدون عنوان')}</div>
        <div class="job-meta">${j.status==='recording'?'🔴 يسجّل':j.status==='done'?'✅ مكتمل':'⏳'} • ⏱️ ${formatTime(j.duration)} • 💾 ${formatSize(j.size)}</div>
        <div class="actions">
          ${j.status==='done'?`<a href="/api/download/${j.id}" class="download">⬇️ تحميل</a>`:''}
          <button class="delete" onclick="deleteJob('${j.id}')">🗑️ حذف</button>
        </div>
      </div>`).join('');
  }catch(e){}
}
async function deleteJob(id){ if(!confirm('حذف؟'))return; await fetch('/api/job/'+id,{method:'DELETE'}); loadJobs(); }
$('#startBtn').addEventListener('click',startRecording);
$('#url').addEventListener('keydown',e=>{if(e.key==='Enter')startRecording();});
loadJobs(); setInterval(loadJobs,10000);
</script>
</body>
</html>
"""

@app.route('/')
def index(): return render_template_string(HTML_PAGE)

@app.route('/health')
def health(): return jsonify({"status":"ok","time":time.time()})

@app.route('/api/record', methods=['POST'])
def start_record():
    data = request.get_json() or {}
    url = data.get('url','').strip()
    if not url: return jsonify({'error':'الرجاء إدخال رابط'}),400
    job_id = str(uuid.uuid4())[:8]
    jobs[job_id] = {'id':job_id,'url':url,'status':'starting','duration':0,'size':0,'title':'جاري التحضير...','created_at':time.strftime('%Y-%m-%d %H:%M'),'file':None,'start_time':time.time()}
    threading.Thread(target=record_stream,args=(job_id,url),daemon=True).start()
    return jsonify({'id':job_id,'status':'started'})

def record_stream(job_id, url):
    job = jobs[job_id]
    job['status'] = 'recording'
    out_template = str(RECORDINGS_DIR / f"{job_id}.%(ext)s")
    def progress_hook(d):
        if d['status']=='downloading':
            job['size'] = d.get('downloaded_bytes',0)
            job['duration'] = time.time() - job['start_time']
            if job['duration'] > MAX_RECORDING_SECONDS: raise yt_dlp.utils.DownloadError("انتهت")
    ydl_opts = {'outtmpl':out_template,'format':'best[ext=mp4]/best','progress_hooks':[progress_hook],'quiet':True,'no_warnings':True,'live_from_start':True,'nocheckcertificate':True}
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url,download=True)
            job['title'] = info.get('title','تسجيل')
            for f in RECORDINGS_DIR.glob(f"{job_id}.*"):
                job['file'] = f.name; job['size'] = f.stat().st_size; break
        job['status'] = 'done'
        job['duration'] = time.time() - job['start_time']
    except Exception as e:
        job['status'] = 'error'; job['error'] = str(e)[:200]

@app.route('/api/status/<job_id>')
def job_status(job_id):
    if job_id not in jobs: return jsonify({'error':'not found'}),404
    j = jobs[job_id]
    if j['status']=='recording':
        total=0
        for f in RECORDINGS_DIR.glob(f"{job_id}*"): total += f.stat().st_size
        j['size']=total
    return jsonify(j)

@app.route('/api/jobs')
def list_jobs(): return jsonify(list(jobs.values()))

@app.route('/api/download/<job_id>')
def download(job_id):
    if job_id not in jobs: return jsonify({'error':'not found'}),404
    j = jobs[job_id]
    if not j.get('file'):
        for f in RECORDINGS_DIR.glob(f"{job_id}.*"): j['file']=f.name; break
    if not j.get('file'): return jsonify({'error':'غير جاهز'}),404
    fp = RECORDINGS_DIR / j['file']
    if not fp.exists(): return jsonify({'error':'غير موجود'}),404
    safe = "".join(c for c in j['title'] if c.isalnum() or c in ' -_')[:50]
    return send_file(str(fp),as_attachment=True,download_name=f"{safe or job_id}.mp4")

@app.route('/api/job/<job_id>', methods=['DELETE'])
def delete_job(job_id):
    if job_id in jobs:
        for f in RECORDINGS_DIR.glob(f"{job_id}.*"):
            try: f.unlink()
            except: pass
        del jobs[job_id]
    return jsonify({'ok':True})

if __name__ == '__main__':
    port = int(os.environ.get('PORT',5000))
    app.run(host='0.0.0.0',port=port)