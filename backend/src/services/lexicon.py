import re,unicodedata
from src.models.entities import TermLexicon
from src.utils import repository as repo
from src.utils.identity import new_id,now

def normalize(term):return unicodedata.normalize('NFKC',term).strip().lower()
def list_lexicons():return repo.all_rows('lexicons')
def create(data):
 terms=[normalize(x) for x in data.terms];stopwords=[normalize(x) for x in data.stopwords]
 if any(not re.fullmatch(r'[a-z0-9一-龥]{1,16}',x) for x in terms):raise ValueError('词项须为1—16个中英文字母/数字，无空格标点')
 if len(set(terms))!=len(terms) or len(set(stopwords))!=len(stopwords):raise ValueError('规范化后词项或停用词重复')
 if not set(stopwords).issubset(terms):raise ValueError('停用词须来自受控词表')
 if not set(terms)-set(stopwords):raise ValueError('移除停用词后词表为空')
 return repo.put('lexicons',TermLexicon(new_id('lexicon'),data.name,data.version,terms,stopwords,now()))
