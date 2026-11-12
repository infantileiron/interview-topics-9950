import {useState} from 'react';
import {savedUser,clearSession} from '../stores/session';
export function useSession(){const [user,setUser]=useState(savedUser);return{user,setUser,logout:()=>{clearSession();setUser(null)}}}
