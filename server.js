'use strict';
const http = require('node:http');
const fs = require('node:fs');
const path = require('node:path');
const { randomUUID } = require('node:crypto');

const PORT = Number(process.env.PORT || 4173);
const STORE_PATH = path.join(__dirname, 'data', 'store.json');
let store = JSON.parse(fs.readFileSync(STORE_PATH, 'utf8'));
let writeQueue = Promise.resolve();
function persist() {
  const snapshot = JSON.stringify(store, null, 2);
  writeQueue = writeQueue.then(() => fs.promises.writeFile(STORE_PATH, snapshot));
  return writeQueue;
}
function send(res, status, payload) {
  res.writeHead(status, {'Content-Type':'application/json; charset=utf-8','Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,PATCH,OPTIONS','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Private-Network':'true'});
  res.end(JSON.stringify(payload));
}
function readBody(req) {
  return new Promise((resolve, reject) => {
    let raw = ''; req.on('data', chunk => { raw += chunk; if (raw.length > 16_384) { reject(new Error('Request body too large')); req.destroy(); } });
    req.on('end', () => { try { resolve(raw ? JSON.parse(raw) : {}); } catch { reject(new Error('Body must be valid JSON')); } });
    req.on('error', reject);
  });
}
function route(req, res) {
  if (req.method === 'OPTIONS') {res.writeHead(204,{'Access-Control-Allow-Origin':'*','Access-Control-Allow-Methods':'GET,POST,PATCH,OPTIONS','Access-Control-Allow-Headers':'Content-Type','Access-Control-Allow-Private-Network':'true'});return res.end();}
  const url = new URL(req.url, `http://${req.headers.host || 'localhost'}`);
  if (req.method === 'GET' && url.pathname === '/api/health') return send(res, 200, {ok:true,service:'eduverse-learning-api'});
  if (req.method === 'GET' && url.pathname === '/api/courses') {
    const q=(url.searchParams.get('q')||'').trim().toLowerCase();
    const level=(url.searchParams.get('level')||'').trim().toLowerCase();
    return send(res,200,{courses:store.courses.filter(c=>(!q||`${c.title} ${c.category} ${c.description}`.toLowerCase().includes(q))&&(!level||level==='all'||c.level.toLowerCase()===level))});
  }
  if (req.method === 'GET' && url.pathname === '/api/profile') return send(res,200,{profile:store.profile});
  if (req.method === 'PATCH' && url.pathname === '/api/profile') return readBody(req).then(async body=>{
    const allowed=['name','bio','dailyGoalMinutes','role','preferences','age','institution'];
    for(const key of allowed) if(body[key]!==undefined){
      if(key==='name'||key==='bio'){if(typeof body[key]!=='string'||body[key].length>(key==='name'?80:280))return send(res,400,{error:`Invalid ${key}`});store.profile[key]=body[key];}
      if(key==='dailyGoalMinutes'){const n=Number(body[key]);if(!Number.isInteger(n)||n<5||n>240)return send(res,400,{error:'dailyGoalMinutes must be between 5 and 240'});store.profile[key]=n;}
      if(key==='role'){if(!['student','teacher','administrator'].includes(body[key]))return send(res,400,{error:'Invalid role'});store.profile[key]=body[key];}
      if(key==='preferences'){if(!body[key]||typeof body[key]!=='object')return send(res,400,{error:'Invalid preferences'});const theme=body[key].theme;if(theme!==undefined){if(!['light','dark','system'].includes(theme))return send(res,400,{error:'Invalid theme'});store.profile.preferences={...store.profile.preferences,theme};}}
      if(key==='age'){if(body[key]!==null&&(!Number.isInteger(Number(body[key]))||Number(body[key])<5||Number(body[key])>120))return send(res,400,{error:'Age must be between 5 and 120'});store.profile.age=body[key]===null?null:Number(body[key]);}
      if(key==='institution'){if(typeof body[key]!=='string'||body[key].length>120)return send(res,400,{error:'Institution is too long'});store.profile.institution=body[key];}
    }
    await persist();send(res,200,{profile:store.profile});
  }).catch(e=>send(res,400,{error:e.message}));
  if (req.method === 'GET' && url.pathname === '/api/progress') return send(res,200,{progress:store.progress,attempts:store.attempts.slice(-20).reverse()});
  if (req.method === 'GET' && url.pathname === '/api/vision/progress') {
    const vision=store.vision||{events:[],completed:{},badges:[]};
    return send(res,200,{vision:{completed:vision.completed||{},badges:vision.badges||[],events:(vision.events||[]).slice(-50).reverse()}});
  }
  if (req.method === 'POST' && url.pathname === '/api/vision/events') return readBody(req).then(async body=>{
    const experimentId=String(body.experimentId||'').slice(0,50),type=body.type;
    if(!/^[a-z0-9-]+$/.test(experimentId)||!['challenge','completed'].includes(type))return send(res,400,{error:'Provide a valid experimentId and event type'});
    const score=Number(body.score??0);if(!Number.isFinite(score)||score<0||score>100)return send(res,400,{error:'score must be between 0 and 100'});
    if(!store.vision)store.vision={events:[],completed:{},badges:[]};
    const vision=store.vision,createdAt=new Date().toISOString();
    const event={id:randomUUID(),experimentId,type,score,createdAt};
    vision.events.push(event);if(vision.events.length>500)vision.events=vision.events.slice(-500);
    if(type==='completed'&&!vision.completed[experimentId])vision.completed[experimentId]={completedAt:createdAt,score};
    const badges={drawing:['sketch-artist','Sketch Artist'], 'air-keyboard':['air-typist','Air Typist'], 'gesture-trainer':['gesture-apprentice','Gesture Apprentice'], chemistry:['lab-explorer','Lab Explorer'], science:['lab-explorer','Lab Explorer']};
    const award=badges[experimentId];if(type==='completed'&&award&&!vision.badges.some(b=>b.id===award[0]))vision.badges.push({id:award[0],title:award[1],awardedAt:createdAt});
    const completedCount=Object.keys(vision.completed).length;store.progress.visionExperimentsCompleted=completedCount;
    if(completedCount>=3&&!vision.badges.some(b=>b.id==='vision-explorer'))vision.badges.push({id:'vision-explorer',title:'Vision Explorer',awardedAt:createdAt});
    await persist();send(res,201,{event,completedCount,badges:vision.badges});
  }).catch(e=>send(res,400,{error:e.message}));
  if (req.method === 'GET' && url.pathname === '/api/resources') {const q=(url.searchParams.get('q')||'').toLowerCase();const type=(url.searchParams.get('type')||'').toLowerCase();return send(res,200,{resources:(store.resources||[]).filter(r=>(!q||`${r.title} ${r.course} ${r.summary} ${r.type}`.toLowerCase().includes(q))&&(!type||r.type.toLowerCase()===type))});}
  if (req.method === 'GET' && url.pathname.startsWith('/api/resources/')) {const item=(store.resources||[]).find(r=>r.id===url.pathname.split('/')[3]);return item?send(res,200,{resource:item}):send(res,404,{error:'Resource not found'});}
  if (req.method === 'GET' && url.pathname === '/api/notifications') return send(res,200,{notifications:store.notifications||[]});
  if (req.method === 'POST' && url.pathname.startsWith('/api/notifications/') && url.pathname.endsWith('/read')) {const item=(store.notifications||[]).find(n=>n.id===url.pathname.split('/')[3]);if(!item)return send(res,404,{error:'Notification not found'});item.read=true;return persist().then(()=>send(res,200,{notification:item}));}
  if (req.method === 'GET' && url.pathname === '/api/teacher') return send(res,200,{teacherData:store.teacherData||{schedule:[],attendance:[],practice:[],tests:[]},roster:[{id:'EV-STU-001',name:'Sanjana Banjare',role:'student',status:'present'},{id:'EV-STU-002',name:'Aarav Mehta',role:'student',status:'present'},{id:'EV-STU-003',name:'Sam Patel',role:'student',status:'absent'}]});
  if (req.method === 'POST' && url.pathname.startsWith('/api/teacher/tests/') && url.pathname.endsWith('/attempts')) return readBody(req).then(async body=>{const id=url.pathname.split('/')[4];const test=(store.teacherData?.tests||[]).find(t=>t.id===id);if(!test)return send(res,404,{error:'Test not found'});if(!test.attempts)test.attempts=[];const attempt={id:randomUUID(),studentId:store.profile.accountId||store.profile.id,answers:body.answers||{},submittedAt:new Date().toISOString()};test.attempts.unshift(attempt);await persist();send(res,201,{attempt});}).catch(e=>send(res,400,{error:e.message}));
  if (req.method === 'POST' && url.pathname.startsWith('/api/teacher/')) return readBody(req).then(async body=>{const kind=url.pathname.split('/')[3];if(!['schedule','attendance','practice','tests'].includes(kind))return send(res,404,{error:'Teacher tool not found'});if(!store.teacherData)store.teacherData={schedule:[],attendance:[],practice:[],tests:[]};const item={id:randomUUID(),...body,createdAt:new Date().toISOString()};store.teacherData[kind].unshift(item);await persist();send(res,201,{item,teacherData:store.teacherData});}).catch(e=>send(res,400,{error:e.message}));
  if (req.method === 'POST' && url.pathname === '/api/feedback') return readBody(req).then(async body=>{if(typeof body.message!=='string'||!body.message.trim())return send(res,400,{error:'Feedback message is required.'});if(!store.feedback)store.feedback=[];const item={id:randomUUID(),category:String(body.category||'general').slice(0,50),message:body.message.trim().slice(0,3000),createdAt:new Date().toISOString()};store.feedback.unshift(item);await persist();send(res,201,{feedback:item});}).catch(e=>send(res,400,{error:e.message}));
  if (req.method === 'GET' && url.pathname === '/api/notes') return send(res,200,{notes:store.notes||[]});
  if (req.method === 'POST' && url.pathname === '/api/notes') return readBody(req).then(async body=>{
    if(typeof body.title!=='string'||!body.title.trim()||body.title.length>100||typeof body.content!=='string'||body.content.length>12000)return send(res,400,{error:'Provide a title and note content (up to 12,000 characters).'});
    if(!store.notes)store.notes=[];const note={id:randomUUID(),title:body.title.trim(),content:body.content,updatedAt:new Date().toISOString()};store.notes.unshift(note);await persist();send(res,201,{note});
  }).catch(e=>send(res,400,{error:e.message}));
  if (req.method === 'GET' && url.pathname === '/api/assignments') return send(res,200,{assignments:store.assignments||[]});
  if (req.method === 'POST' && url.pathname === '/api/assignments') return readBody(req).then(async body=>{
    if(typeof body.title!=='string'||!body.title.trim()||body.title.length>120||typeof body.description!=='string'||!body.description.trim())return send(res,400,{error:'Assignment title and instructions are required.'});
    if(!store.assignments)store.assignments=[];const item={id:randomUUID(),title:body.title.trim(),course:String(body.course||'General').slice(0,100),description:body.description.trim().slice(0,2000),dueDate:String(body.dueDate||'').slice(0,20),status:'assigned',submission:'',feedback:''};store.assignments.unshift(item);await persist();send(res,201,{assignment:item});
  }).catch(e=>send(res,400,{error:e.message}));
  if (req.method === 'POST' && url.pathname.startsWith('/api/assignments/') && url.pathname.endsWith('/submit')) return readBody(req).then(async body=>{
    const id=url.pathname.split('/')[3],item=(store.assignments||[]).find(a=>a.id===id);if(!item)return send(res,404,{error:'Assignment not found'});if(typeof body.submission!=='string'||!body.submission.trim()||body.submission.length>8000)return send(res,400,{error:'Submission text is required (up to 8,000 characters).'});item.submission=body.submission.trim();item.status='submitted';await persist();send(res,200,{assignment:item});
  }).catch(e=>send(res,400,{error:e.message}));
  if (req.method === 'GET' && url.pathname === '/api/syllabus') return send(res,200,{tracks:[{id:'web',title:'Web development',modules:['HTML & semantic structure','CSS layouts and responsive design','JavaScript fundamentals','DOM, events, and browser APIs','React components and state','APIs, Git, and deployment']},{id:'dsa',title:'Data structures & algorithms',modules:['Complexity and Big O','Arrays, strings, and hash maps','Stacks, queues, and linked lists','Recursion and trees','Sorting and binary search','Graphs and dynamic programming']},{id:'backend',title:'Backend engineering',modules:['HTTP and REST fundamentals','Node.js and Express','Data modeling and databases','Authentication and authorization','Validation, errors, and security','Testing and deployment']} ]});
  if (req.method === 'POST' && url.pathname === '/api/attempts') return readBody(req).then(async body=>{
    if(body.activityId!=='binary-search-boundary'||!['left','right'].includes(body.answer))return send(res,400,{error:'Provide a valid binary-search activity and answer.'});
    const correct=body.answer==='right';
    const previous=store.progress.concepts['search-boundaries'];
    const attempt={id:randomUUID(),activityId:body.activityId,answer:body.answer,correct,createdAt:new Date().toISOString()};
    store.attempts.push(attempt);
    previous.evidenceCount+=1;
    // Small, bounded illustrative mastery update based on a validated attempt.
    previous.mastery=Math.min(100,Math.max(0,Math.round(previous.mastery+(correct?5:-2))));
    if(correct)store.progress.completedChallenges+=1;
    await persist();send(res,201,{attempt,progress:store.progress});
  }).catch(e=>send(res,400,{error:e.message}));
  send(res,404,{error:'Route not found'});
}
http.createServer((req,res)=>{try{Promise.resolve(route(req,res)).catch(()=>send(res,500,{error:'Internal server error'}));}catch{send(res,500,{error:'Internal server error'});}}).listen(PORT,'127.0.0.1',()=>console.log(`EduVerse API listening on http://127.0.0.1:${PORT}`));
