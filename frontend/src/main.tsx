import React, { useEffect, useMemo, useState } from 'react';
import { createRoot } from 'react-dom/client';
import './style.css';

type Status = 'saved' | 'applied' | 'interview' | 'offer' | 'rejected';
type Application = { id: number; company: string; role: string; status: Status; url: string | null; created_at: string; details: Record<string,string> };
const statuses: Status[] = ['saved', 'applied', 'interview', 'offer', 'rejected'];
const fields: {key:string; label:string}[] = [
  {key:'date',label:'DATE'}, {key:'claude_link',label:'CLAUDE LINK'},
  {key:'company',label:'COMPANY'}, {key:'role',label:'ROLE'}, {key:'role_id',label:'ROLE ID'},
  {key:'location',label:'LOCATION'}, {key:'salary',label:'SALARY'},
  {key:'resume_saved_as',label:'RESUME SAVED AS'}, {key:'hr_name',label:'HR name'},
  {key:'hr_email',label:'HR email'}, {key:'original_status',label:'STATUS (sheet)'},
  {key:'latest_update',label:'LATEST UPDATE'}, {key:'extra_notes',label:'EXTRA NOTES'},
  {key:'recruiter_reference',label:'RECRUITER / REFERENCE'}, {key:'contact',label:'CONTACT'},
  {key:'phone_number',label:'PHONE NUMBER'}, {key:'mutual',label:'MUTUAL'},
  {key:'claude_link_extra',label:'CLAUDE LINK (second column)'}
];
const API = import.meta.env.VITE_API_URL ?? 'http://localhost:8000';
const value = (item:Application, key:string) => key==='company'||key==='role' ? item[key] : item.details[key] ?? '';
function App() {
  const [items,setItems] = useState<Application[]>([]);
  const [company,setCompany]=useState(''); const [role,setRole]=useState('');
  const [url,setUrl]=useState(''); const [query,setQuery]=useState('');
  const [view,setView]=useState<'table'|'board'>('table');
  const [editing,setEditing]=useState<Application|null>(null);
  const [error,setError]=useState(''); const [importResult,setImportResult]=useState('');
  async function refresh() {
    try { const r=await fetch(`${API}/applications-with-details`); if(!r.ok) throw Error(); setItems(await r.json()); setError(''); }
    catch { setError('Cannot connect to API. Check Docker Desktop.'); }
  }
  useEffect(()=>{void refresh();},[]);
  const filtered=useMemo(()=>items.filter(i=>[i.company,i.role,i.status,...Object.values(i.details)].some(v=>String(v).toLowerCase().includes(query.toLowerCase()))),[items,query]);
  async function importCsv(file:File) {
    const form=new FormData();form.append('file',file);setImportResult('Importing…');
    try { const r=await fetch(`${API}/imports/google-sheet-csv`,{method:'POST',body:form});const d=await r.json();if(!r.ok)throw Error(d.detail||'Import failed');setImportResult(`Created ${d.created}, updated ${d.updated}, skipped ${d.skipped}.`);await refresh(); }
    catch(e){setImportResult(e instanceof Error?e.message:'Import failed');}
  }
  async function add(e:React.FormEvent){e.preventDefault();try{const r=await fetch(`${API}/applications`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({company,role,url:url||null})});if(!r.ok)throw Error();setCompany('');setRole('');setUrl('');await refresh();}catch{setError('Could not add application');}}
  async function move(id:number,status:Status){try{const r=await fetch(`${API}/applications/${id}`,{method:'PATCH',headers:{'Content-Type':'application/json'},body:JSON.stringify({status})});if(!r.ok)throw Error();await refresh();}catch{setError('Could not change status');}}
  async function remove(id:number){if(!window.confirm('Delete this application?'))return;try{const r=await fetch(`${API}/applications/${id}`,{method:'DELETE'});if(!r.ok)throw Error();await refresh();}catch{setError('Could not delete application');}}
  async function save(e:React.FormEvent){e.preventDefault();if(!editing)return;try{const r=await fetch(`${API}/applications/${editing.id}/full`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(editing)});if(!r.ok)throw Error();setEditing(null);await refresh();}catch{setError('Could not save details');}}
  function editField(key:string,v:string){setEditing(prev=>!prev?prev:key==='company'||key==='role'?{...prev,[key]:v}:{...prev,details:{...prev.details,[key]:v}});}
  return <main>
    <header><div><p className="eyebrow">YOUR APPLICATION WORKSPACE</p><h1>CareerFlow</h1><p>All the columns from your application spreadsheet, in one place.</p></div><span className="badge">{items.length} applications</span></header>
    <section className="panel"><h2>Add an application</h2><form onSubmit={add}><input placeholder="Company" aria-label="Company" required value={company} onChange={e=>setCompany(e.target.value)}/><input placeholder="Role" aria-label="Role" required value={role} onChange={e=>setRole(e.target.value)}/><input placeholder="Job URL (optional)" aria-label="Job URL" value={url} onChange={e=>setUrl(e.target.value)}/><button>Add</button></form></section>
    <section className="panel"><h2>Import your Google Sheet</h2><p>Export Sheet1 as CSV and upload it here. Every named header is preserved, including the second Claude Link column.</p><input type="file" accept=".csv,text/csv" aria-label="Upload CSV" onChange={e=>{const f=e.target.files?.[0];if(f)void importCsv(f);e.currentTarget.value='';}}/>{importResult&&<p role="status">{importResult}</p>}</section>
    <section className="toolbar"><input aria-label="Search applications" placeholder="Search companies, recruiters, notes, roles…" value={query} onChange={e=>setQuery(e.target.value)}/><button className={view==='table'?'active':''} onClick={()=>setView('table')}>Spreadsheet view</button><button className={view==='board'?'active':''} onClick={()=>setView('board')}>Kanban view</button></section>
    {error&&<p className="error" role="alert">{error}</p>}
    {view==='table'?<section className="table-scroll"><table><thead><tr><th>EDIT</th>{fields.map(f=><th key={f.key}>{f.label}</th>)}<th>CAREERFLOW STAGE</th></tr></thead><tbody>{filtered.map(i=><tr key={i.id}><td><button onClick={()=>setEditing({...i,details:{...i.details}})}>Edit</button></td>{fields.map(f=><td key={f.key} title={value(i,f.key)}>{value(i,f.key)||'—'}</td>)}<td><select value={i.status} onChange={e=>void move(i.id,e.target.value as Status)}>{statuses.map(s=><option key={s}>{s}</option>)}</select></td></tr>)}</tbody></table></section>
    :<section className="board">{statuses.map(status=><div className="column" key={status}><h2>{status.toUpperCase()} <small>{filtered.filter(i=>i.status===status).length}</small></h2>{filtered.filter(i=>i.status===status).map(i=><article className="card" key={i.id}><strong>{i.company}</strong><p>{i.role}</p><p>{i.details.location||''}</p><button onClick={()=>setEditing({...i,details:{...i.details}})}>View / edit details</button><div className="actions"><select value={i.status} onChange={e=>void move(i.id,e.target.value as Status)}>{statuses.map(s=><option key={s}>{s}</option>)}</select><button className="remove" onClick={()=>void remove(i.id)}>×</button></div></article>)}</div>)}</section>}
    {editing&&<div className="overlay" role="presentation" onMouseDown={e=>{if(e.target===e.currentTarget)setEditing(null);}}><section className="editor" role="dialog" aria-modal="true" aria-label="Edit application"><div className="editor-head"><h2>Edit application</h2><button onClick={()=>setEditing(null)}>Close</button></div><form onSubmit={save} className="editor-form">{fields.map(f=><label key={f.key}>{f.label}{['latest_update','extra_notes'].includes(f.key)?<textarea value={value(editing,f.key)} onChange={e=>editField(f.key,e.target.value)}/>:<input value={value(editing,f.key)} onChange={e=>editField(f.key,e.target.value)} required={f.key==='company'}/>}</label>)}<label>CAREERFLOW STAGE<select value={editing.status} onChange={e=>setEditing({...editing,status:e.target.value as Status})}>{statuses.map(s=><option key={s}>{s}</option>)}</select></label><label>JOB URL<input value={editing.url||''} onChange={e=>setEditing({...editing,url:e.target.value||null})}/></label><button className="save" type="submit">Save changes</button></form></section></div>}
  </main>;
}
createRoot(document.getElementById('root')!).render(<App/>);
