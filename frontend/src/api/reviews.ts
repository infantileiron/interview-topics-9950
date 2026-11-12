import {request} from './client';import type {Review} from '../types/entities';export const list=()=>request<Review[]>('/reviews');export const create=(data:unknown)=>request<Review>('/reviews','POST',data);
export const decide=(id:string,data:unknown)=>request<Review>('/reviews/'+id,'PATCH',data);
