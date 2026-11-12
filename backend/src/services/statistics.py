import hashlib,json
import numpy as np
from src.services.tfidf import vectorize,cosine_neighbors
from src.services.nmf import factorize

def analyze(rows,lexicon,study):
 vectors=vectorize(rows,lexicon);matrix=vectors['matrix'];nmf=factorize(matrix,study['topic_count'],study['seed'],study['max_iter'],study['tolerance']);w=np.array(nmf['w']);h=np.array(nmf['h']);topics=[]
 for k,weights in enumerate(h):
  order=sorted(range(len(weights)),key=lambda j:(-float(weights[j]),vectors['vocabulary'][j]))[:8];total=float(weights.sum())
  topics.append({'id':f'T{k+1:02d}','top_terms':[{'term':vectors['vocabulary'][j],'weight':float(weights[j]),'display_fraction':float(weights[j]/total) if total else 0} for j in order],'raw_h_sum':total})
 documents=[]
 for i,r in enumerate(vectors['valid']):
  total=float(w[i].sum());documents.append({'doc_id':r['doc_id'],'excerpt':r['text'][:100],'weights':w[i].tolist(),'display_fractions':(w[i]/total).tolist() if total else [0.]*len(topics),'unknown_characters':r['unknown_characters']})
 return {'documents':documents,'document_count':len(rows),'included':len(documents),'isolated':vectors['isolated'],'feature_count':len(vectors['vocabulary']),'vocabulary':vectors['vocabulary'],'df':vectors['df'],'idf':vectors['idf'],'sparse_tfidf':vectors['sparse_vectors'],'unused_terms':vectors['unused_terms'],'topics':topics,'neighbors':cosine_neighbors(matrix,[r['doc_id'] for r in vectors['valid']]),'nmf':nmf,'lexicon_snapshot':lexicon,'study':study,'checksum':hashlib.sha256(json.dumps({'rows':rows,'lexicon':lexicon,'study':study},sort_keys=True).encode()).hexdigest(),'limitations':['分词采用NFKC/lower后最长词表匹配，未知字母/汉字跳过并计数，标点/空白跳过；停用词不计入TF','全零文档先隔离，不进入IDF分母/余弦/NMF；TF=词频/有效token总数，IDF=ln((1+N)/(1+df))+1','NMF输入为未做L2归一的TF-IDF；余弦近邻单独做行L2归一，不把自身当近邻','固定seed乘法更新最小化Frobenius重建误差，收敛为至少10次迭代后相对误差变化小于阈值；达到上限不伪称收敛','原始W/H完整保存并用于W@H；主题词display_fraction和文档display_fractions仅展示归一，不替换原矩阵','主题编号不是语义真值；名称由人工在复核记录中版本化保存，无外部LLM/分词API']}
