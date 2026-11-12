import csv,io
from dataclasses import asdict
from src.models.entities import CorpusDataset
from src.utils import repository as repo
from src.utils.identity import new_id,now
from src.constants.domain import MAX_DOCUMENTS,MAX_CHARACTERS

def summary(item):return {k:v for k,v in item.items() if k!='rows'}|{'row_count':len(item['rows']),'characters':sum(len(r['text']) for r in item['rows'])}
def list_datasets():return [summary(x) for x in repo.all_rows('datasets')]
def detail(id):return repo.get('datasets',id)
def rename(id,data):
 item=repo.get('datasets',id);item['name']=data.name;repo.put('datasets',item);return summary(item)
def create(data):
 reader=csv.DictReader(io.StringIO(data.csv_text.lstrip('\ufeff')))
 if not {'doc_id','text'}.issubset(reader.fieldnames or []):raise ValueError('CSV需要doc_id,text，内容须为匿名模拟访谈')
 rows=[];seen=set()
 for n,r in enumerate(reader,2):
  if n>MAX_DOCUMENTS+1:raise ValueError('最多600篇文档')
  id=(r.get('doc_id') or '').strip();text=(r.get('text') or '').strip()
  if not id or id in seen or not 1<=len(text)<=MAX_CHARACTERS:raise ValueError(f'第{n}行编号/文本为空、重复或超过2000字')
  seen.add(id);rows.append({'doc_id':id,'text':text})
 if len(rows)<2:raise ValueError('至少2篇文档')
 item=CorpusDataset(new_id('ds'),data.name,data.source,rows,now());repo.put('datasets',item);return summary(asdict(item))
