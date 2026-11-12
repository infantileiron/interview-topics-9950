import numpy as np
from src.constants.domain import EPSILON

def factorize(matrix,topic_count,seed=2305,max_iter=250,tolerance=.00001):
 v=np.asarray(matrix,dtype=float)
 if v.ndim!=2 or not v.size or not np.isfinite(v).all() or np.any(v<0) or not np.any(v>0):raise ValueError('NMF输入必须是非空、非负、有限且非零矩阵')
 if not isinstance(topic_count,int) or not 1<=topic_count<=min(v.shape[0],v.shape[1],8):raise ValueError('主题数须≤有效文档数/有效词数/8')
 if not isinstance(max_iter,int) or not 10<=max_iter<=600 or not np.isfinite(tolerance) or not 0<tolerance<=.01:raise ValueError('迭代次数或收敛阈值无效')
 rng=np.random.default_rng(seed);scale=np.sqrt(float(v.mean())/topic_count);w=(rng.random((v.shape[0],topic_count))+.1)*scale;h=(rng.random((topic_count,v.shape[1]))+.1)*scale
 previous=float(np.linalg.norm(v-w@h));history=[{'iteration':0,'error':previous}];converged=False;relative_change=None
 for iteration in range(1,max_iter+1):
  h*=((w.T@v)/(w.T@w@h+EPSILON));w*=((v@h.T)/(w@h@h.T+EPSILON))
  error=float(np.linalg.norm(v-w@h));relative_change=abs(previous-error)/max(previous,EPSILON)
  if iteration%10==0 or iteration==max_iter:history.append({'iteration':iteration,'error':error})
  if iteration>=10 and relative_change<tolerance:
   converged=True
   if history[-1]['iteration']!=iteration:history.append({'iteration':iteration,'error':error})
   break
  previous=error
 return {'w':w.tolist(),'h':h.tolist(),'topic_count':topic_count,'iterations':iteration,'converged':converged,'relative_change':relative_change,'error':error,'relative_error':error/float(np.linalg.norm(v)),'error_history':history,'seed':seed,'warning':'' if converged else '已达到迭代上限，尚未满足相对误差变化阈值；结果可复核但不声明收敛'}
