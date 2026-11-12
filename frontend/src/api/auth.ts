import {request} from './client';
import type {User} from '../types/entities';
export const login=(email:string,password:string)=>request<{access_token:string;user:User}>('/auth/login','POST',{email,password});
