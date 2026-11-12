import random
from src.utils import repository as repo
from src.utils.identity import now
from src.utils.security import hash_password
from src.services.statistics import analyze
POOLS=[['公交','换乘','步行','车站','候车'],['照护','陪伴','长者','家务','休息'],['手机','应用','登录','通知','数据'],['公园','座椅','照明','安静','树荫'],['食材','烹饪','采购','新鲜','份量'],['阅读','课程','练习','图书','讨论']]
STOP=['我们','这个','提到','然后','感觉']
def demo_rows():
 rng=random.Random(2305);rows=[]
 for i in range(480):
  p=POOLS[i%6];words=rng.sample(p,4);text=f'我们提到{words[0]}、{words[1]}和{words[2]}。这个{words[0]}需要{words[3]}，然后我们感觉{words[1]}值得讨论。'
  if i%17==0:text+=f'还有{POOLS[(i+1)%6][0]}与{POOLS[(i+1)%6][1]}。'
  if i%79==0:text='没有词典涵盖的记录'
  rows.append({'doc_id':f'LW-{i+1:04d}','text':text})
 return rows

def seed():
 repo.init_db()
 for role,name in [('admin','议题复核研究员'),('analyst','语料分析员'),('viewer','研究观察员')]:
  email=f'{role}@liwen.test';repo.put('users',{'id':email,'email':email,'name':name,'role':role,'password_hash':hash_password('Topic2026!')},insert_only=True)
 rows=demo_rows();repo.put('datasets',{'id':'ds-interview','name':'11月匿名访谈 · 480篇','source':'interview_corpus_202611.csv','rows':rows,'created_at':now()},insert_only=True)
 lexicon={'id':'lexicon-v1','name':'访谈受控词表与停用词','version':'2026.11-v1','terms':[x for p in POOLS for x in p]+STOP,'stopwords':STOP,'created_at':now()};repo.put('lexicons',lexicon,insert_only=True)
 study={'id':'study-themes','name':'访谈线索六主题分解','dataset_id':'ds-interview','lexicon_id':'lexicon-v1','topic_count':6,'max_iter':250,'tolerance':.00001,'seed':2305,'created_at':now()};repo.put('studies',study,insert_only=True)
 repo.put('runs',{'id':'run-demo','study_id':'study-themes','status':'completed','result':analyze(rows,lexicon,study),'error':'','created_at':now()},insert_only=True)
 names={f'T{i+1:02d}':f'访谈线索{["一","二","三","四","五","六"][i]}（研究组编号）' for i in range(6)}
 repo.put('reviews',{'id':'review-demo','run_id':'run-demo','comment':'模拟研究组以编号命名，不把NMF主题当语义真值；实际命名需逐篇复核。','theme_names':names,'status':'approved','reviewer':'admin@liwen.test','created_at':now()},insert_only=True)
 repo.put('reports',{'id':'report-demo','run_id':'run-demo','review_id':'review-demo','title':'栎文访谈议题索引复核册','created_at':now()},insert_only=True)
 return {t:len(repo.all_rows(t)) for t in ('users','datasets','lexicons','studies','runs','reviews','reports')}
