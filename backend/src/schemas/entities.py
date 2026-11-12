from pydantic import BaseModel,Field,ConfigDict
from typing import Literal
class InputModel(BaseModel):
 model_config=ConfigDict(allow_inf_nan=False)
class LoginInput(InputModel):
 email:str
 password:str
class DatasetInput(InputModel):
 name:str=Field(min_length=2,max_length=100)
 source:str=Field(default='interview_corpus_202611.csv',max_length=100)
 csv_text:str=Field(min_length=20,max_length=1800000)
class RenameDataset(InputModel):
 name:str=Field(min_length=2,max_length=100)
class LexiconInput(InputModel):
 name:str=Field(min_length=2,max_length=100)
 version:str=Field(default='v1',min_length=1,max_length=40)
 terms:list[str]=Field(min_length=2,max_length=80)
 stopwords:list[str]=Field(default_factory=list,max_length=80)
class TopicStudyInput(InputModel):
 name:str=Field(min_length=2,max_length=100)
 dataset_id:str
 lexicon_id:str
 topic_count:int=Field(default=6,ge=1,le=8)
 max_iter:int=Field(default=250,ge=10,le=600)
 tolerance:float=Field(default=.00001,ge=.00000001,le=.01)
 seed:int=Field(default=2305,ge=0,le=2147483647)
class RunInput(InputModel):
 study_id:str
class ReviewInput(InputModel):
 run_id:str
 comment:str=Field(min_length=5,max_length=2000)
 theme_names:dict[str,str]
class DecisionInput(InputModel):
 status:Literal['approved','rejected']
 comment:str=Field(min_length=5,max_length=2000)
class ReportInput(InputModel):
 run_id:str
 review_id:str
 title:str=Field(min_length=2,max_length=100)
