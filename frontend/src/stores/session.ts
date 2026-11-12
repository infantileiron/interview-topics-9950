import type {User} from '../types/entities';
export function savedUser():User|null {try{return JSON.parse(sessionStorage.getItem('topic-user')||'null')}catch{return null}}
export function saveSession(token:string,user:User){sessionStorage.setItem('topic-token',token);sessionStorage.setItem('topic-user',JSON.stringify(user))}
export function clearSession(){sessionStorage.removeItem('topic-token');sessionStorage.removeItem('topic-user')}
