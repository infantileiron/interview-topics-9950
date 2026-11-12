import math
import numpy as np
from src.services.tokenize import tokenize

def vectorize(rows,lexicon):
 terms=set(lexicon['terms'])-set(lexicon['stopwords'])
 if not terms:raise ValueError('有效受控词表为空')
 valid=[];isolated=[]
 for r in rows:
  tok=tokenize(r['text'],lexicon['terms'],lexicon['stopwords'])
  item={**r,**tok}
  if not tok['tokens']:isolated.append({'doc_id':r['doc_id'],'reason':'无有效受控词项（空词向量）','unknown_characters':tok['unknown_characters']})
  else:valid.append(item)
 if not valid:raise ValueError('全部文档为空词向量，不能计算TF-IDF/NMF；请复核词表与停用词')
 vocabulary=sorted(set(t for r in valid for t in r['counts']));n=len(valid);df=[sum(t in r['counts'] for r in valid) for t in vocabulary];idf=[math.log((1+n)/(1+d))+1 for d in df]
 matrix=np.array([[r['counts'].get(t,0)/len(r['tokens'])*idf[j] for j,t in enumerate(vocabulary)] for r in valid],dtype=float)
 sparse=[{'doc_id':r['doc_id'],'token_count':len(r['tokens']),'unknown_characters':r['unknown_characters'],'nonzero':[[j,float(v)] for j,v in enumerate(matrix[i]) if v>0]} for i,r in enumerate(valid)]
 return {'valid':valid,'isolated':isolated,'vocabulary':vocabulary,'df':df,'idf':idf,'matrix':matrix,'sparse_vectors':sparse,'unused_terms':sorted(terms-set(vocabulary))}
def cosine_neighbors(matrix,ids,limit=3):
 norms=np.linalg.norm(matrix,axis=1)
 if np.any(norms<=0):raise ValueError('余弦输入含零向量')
 normalized=matrix/norms[:,None];similarity=np.clip(normalized@normalized.T,0,1);result=[]
 for i,id in enumerate(ids):
  others=sorted((j for j in range(len(ids)) if j!=i),key=lambda j:(-round(float(similarity[i,j]),12),ids[j]))[:limit]
  result.append({'doc_id':id,'neighbors':[{'doc_id':ids[j],'similarity':float(similarity[i,j])} for j in others]})
 return result
