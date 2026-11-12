import csv,io
from fastapi import HTTPException
from src.models.entities import Report
from src.config.settings import ARTIFACT_DIR
from src.utils import repository as repo
from src.utils.identity import new_id,now

def safe_cell(value):return "'"+value if isinstance(value,str) and value.lstrip().startswith(('=','+','-','@')) else value
def list_reports():return repo.all_rows('reports')
def create(data):
 run,review=repo.get('runs',data.run_id),repo.get('reviews',data.review_id)
 if review['status']!='approved' or review['run_id']!=run['id'] or run['status']!='completed':raise ValueError('报告必须引用该运行已批准的人工命名复核')
 report=repo.put('reports',Report(new_id('rpt'),data.run_id,data.review_id,data.title,now()));ARTIFACT_DIR.mkdir(parents=True,exist_ok=True);(ARTIFACT_DIR/(report['id']+'.csv')).write_text(download(report['id']),encoding='utf-8');return report
def build_download(report,run,review):
 """根据报告记录、运行结果与已批准复核在内存中重建CSV文本（纯函数，不读库不落盘）。"""
 r=run['result'];out=io.StringIO();w=csv.writer(out);m=r['nmf']
 w.writerow(['report','documents','included','isolated','features','iterations','converged','frobenius_error','seed','lexicon_version','checksum']);w.writerow([safe_cell(report['title']),r['document_count'],r['included'],len(r['isolated']),r['feature_count'],m['iterations'],m['converged'],m['error'],m['seed'],safe_cell(r['lexicon_snapshot']['version']),r['checksum']])
 w.writerow([]);w.writerow(['topic_id','human_name','term','raw_h_weight','display_fraction'])
 for t in r['topics']:
  for term in t['top_terms']:w.writerow([t['id'],safe_cell(review['theme_names'][t['id']]),safe_cell(term['term']),term['weight'],term['display_fraction']])
 w.writerow([]);w.writerow(['doc_id','topic_id','raw_w_weight','display_fraction'])
 for d in r['documents']:
  for k,t in enumerate(r['topics']):w.writerow([safe_cell(d['doc_id']),t['id'],d['weights'][k],d['display_fractions'][k]])
 w.writerow([]);w.writerow(['doc_id','neighbor_id','cosine_similarity'])
 for d in r['neighbors']:
  for n in d['neighbors']:w.writerow([safe_cell(d['doc_id']),safe_cell(n['doc_id']),n['similarity']])
 w.writerow([]);w.writerow(['isolated_doc','reason'])
 for d in r['isolated']:w.writerow([safe_cell(d['doc_id']),d['reason']])
 return '\ufeff'+out.getvalue()
def download(id):
 report=repo.get('reports',id);run=repo.get('runs',report['run_id']);review=repo.get('reviews',report['review_id'])
 if review['status']!='approved':raise HTTPException(403,'\u590d\u6838\u672a\u901a\u8fc7')
 return build_download(report,run,review)
