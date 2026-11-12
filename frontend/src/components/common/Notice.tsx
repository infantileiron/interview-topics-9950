export default function Notice({error}:{error:string}){return error?<div role="alert" className="notice">{error} <button onClick={()=>location.reload()}>重新加载</button></div>:null}
