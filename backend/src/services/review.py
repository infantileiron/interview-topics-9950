from fastapi import HTTPException
from src.models.entities import ThemeReview
from src.utils import repository as repo
from src.utils.identity import new_id,now

def list_reviews():return repo.all_rows('reviews')
def create(data,user):
 run=repo.get('runs',data.run_id)
 if run['status']!='completed':raise ValueError('仅完成的主题运行可复核')
 required={t['id'] for t in run['result']['topics']};names={k:v.strip() for k,v in data.theme_names.items()}
 if set(names)!=required or any(not 1<=len(v)<=40 for v in names.values()) or len(set(names.values()))!=len(names):raise ValueError('请为每个主题编号提供唯一的1—40字人工名称')
 if any(r['run_id']==data.run_id and r['status'] in ('pending','approved') for r in repo.all_rows('reviews')):raise HTTPException(409,'该运行已有待审或通过复核')
 return repo.put('reviews',ThemeReview(new_id('rev'),data.run_id,data.comment,names,created_at=now()))
def decide(id,data,user):
 item=repo.get('reviews',id)
 if item['status']!='pending':raise HTTPException(409,'该复核已处理')
 item.update(status=data.status,comment=data.comment,reviewer=user['email']);return repo.put('reviews',item)
