from dataclasses import dataclass,field
from typing import Any
@dataclass
class CorpusDataset:
 id:str
 name:str
 source:str
 rows:list[dict]
 created_at:str=''
@dataclass
class TermLexicon:
 id:str
 name:str
 version:str
 terms:list[str]
 stopwords:list[str]
 created_at:str=''
@dataclass
class TopicStudy:
 id:str
 name:str
 dataset_id:str
 lexicon_id:str
 topic_count:int=6
 max_iter:int=250
 tolerance:float=.00001
 seed:int=2305
 created_at:str=''
@dataclass
class TopicRun:
 id:str
 study_id:str
 status:str='queued'
 result:dict[str,Any]=field(default_factory=dict)
 error:str=''
 created_at:str=''
@dataclass
class ThemeReview:
 id:str
 run_id:str
 comment:str
 theme_names:dict[str,str]=field(default_factory=dict)
 status:str='pending'
 reviewer:str=''
 created_at:str=''
@dataclass
class Report:
 id:str
 run_id:str
 review_id:str
 title:str
 created_at:str=''
