export const topicId=(i:number)=>'T'+String(i+1).padStart(2,'0');
export function humanNames(text:string){return Object.fromEntries(text.split(String.fromCharCode(10)).map(x=>x.trim()).filter(Boolean).map((x,i)=>[topicId(i),x]))}
