import { StrictMode, useEffect, useState } from "react";
import { createRoot } from "react-dom/client";
import { call, type Item, type Source } from "./rpc";
import "./style.css";

type Route = {tab:string;branch:string|null;path:string;revision:string|null;history:boolean;offset:number};
function readRoute():Route {
  const [tab, query] = location.hash.slice(1).split("?");
  const q = new URLSearchParams(query);
  return {tab:tab || "code",branch:q.get("branch"),path:q.get("path") || "",
    revision:q.get("rev"),history:q.has("history"),offset:Number(q.get("offset") || 0)};
}
function href(r:Route) {
  const q = new URLSearchParams();
  if(r.branch) q.set("branch",r.branch);
  if(r.path) q.set("path",r.path);
  if(r.revision) q.set("rev",r.revision);
  if(r.history) q.set("history","1");
  if(r.offset) q.set("offset",String(r.offset));
  return "#"+r.tab+(q.size ? "?"+q : "");
}
function Code({s,r}:{s:Source;r:Route}) {
  const pin = {...r,branch:s.branch,revision:s.commit?.id ?? null};
  const parts = r.path ? r.path.split("/") : [];
  return <>
    <div className="toolbar"><select aria-label="Source branch" value={s.branch ?? ""} onChange={e=>{
      location.hash=href({...r,branch:e.target.value || null,path:"",revision:null,history:false,offset:0});
    }}>
      {(s.detached || !s.branches.length) && <option value="">{s.detached ? "Detached HEAD" : "No branches"}</option>}
      {s.branches.map(b=><option key={b}>{b}</option>)}</select>
      <nav aria-label="File path"><a href={href({...pin,path:"",history:false})}>{s.name}</a>
      {parts.map((p,i)=><span key={i}> / <a href={href({...pin,path:parts.slice(0,i+1).join("/"),history:false})}>{p}</a></span>)}</nav></div>
    {!s.commit ? <article><h2>No commits yet</h2><p>Add a file and create your first Git commit to browse it here.</p></article> :
    r.history ? <article><h2>Commit history</h2>{s.commits.map(c=><div className="row" key={c.id}>
      <a href={href({...pin,revision:c.id,path:"",history:false,offset:0})}>{c.title || c.id.slice(0,8)}</a>
      <small>{c.author} · {c.date.slice(0,10)} · {c.id.slice(0,8)}</small></div>)}
      <div className="pages">{r.offset>0 && <a href={href({...pin,offset:Math.max(0,r.offset-50)})}>Newer commits</a>}
      {s.more && <a href={href({...pin,offset:r.offset+50})}>Older commits</a>}</div></article> :
    <article><div className="latest"><div><strong>{s.commit.title}</strong><small>{s.commit.author} · {s.commit.date.slice(0,10)} · {s.commit.id.slice(0,8)}</small></div>
      <a href={href({...pin,path:"",history:true,offset:0})}>History</a></div>
      {s.notice ? <p>{s.notice}</p> : s.text !== null ? <pre>{s.text.split("\n").map((line,i)=><div key={i}><i>{i+1}</i>{line}</div>)}</pre> :
      s.entries.map(e=><div className="row" key={e.name}><a href={href({...pin,path:[...parts,e.name].join("/")})}>{e.name}</a>
        <small>{({tree:"Directory",blob:"File",symlink:"Symbolic link",submodule:"Submodule"} as Record<string,string>)[e.kind]}</small></div>)}
    </article>}</>;
}
function App() {
  const [route,go]=useState(readRoute);
  const [source,setSource]=useState<Source|null>(null);
  const [name,setName]=useState("");
  const [items,setItems]=useState<Item[]>([]);
  const [busy,setBusy]=useState(true);
  const [error,setError]=useState("");
  useEffect(()=>{const change=()=>go(readRoute());window.addEventListener("hashchange",change);
    return ()=>window.removeEventListener("hashchange",change);},[]);
  useEffect(()=>{
    let active=true;
    setBusy(true);setError("");
    async function load(){
      const {tab,...params}=route;
      if(tab==="code"){
        const s=await call("code.browse",params);
        if(active){setName(s.name);setSource(s);}
      }else if(tab==="issues" || tab==="pulls"){
        const [ctx,rows]=await Promise.all([call("repo.get",{}),call(tab==="issues"?"issues.list":"pulls.list",{})]);
        if(active){setName(ctx.name);setItems(rows);}
      }else throw Error("Unknown page");
    }
    load().catch(()=>{if(active)setError("Could not load this repository view.");})
      .finally(()=>{if(active)setBusy(false);});
    return ()=>{active=false;};
  },[route]);
  return <><header><small>Git-centric</small><h1>{name || "Repository"}</h1>
    <nav aria-label="Repository">{[["code","Code"],["issues","Issues"],["pulls","Pull requests"]].map(([tab,label])=>
    <a key={tab} href={"#"+tab} aria-current={route.tab===tab?"page":undefined}>{label}</a>)}</nav></header>
    <main>{busy ? <p role="status">Loading…</p> : error ? <p role="alert">{error} <button onClick={()=>go(readRoute())}>Retry</button></p> :
      route.tab==="code" && source ? <Code s={source} r={route}/> : <article><h2>{route.tab==="issues"?"Issues":"Pull requests"}</h2>
      {items.length ? items.map(i=><div className="row" key={i.id}><strong>{i.title}</strong><small>{i.closed?"Closed":"Open"}</small></div>) :
      <p>No {route.tab==="issues"?"issues":"pull requests"} yet.</p>}</article>}</main></>;
}
createRoot(document.getElementById("root")!).render(<StrictMode><App/></StrictMode>);
