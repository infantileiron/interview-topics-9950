import unicodedata
from collections import Counter

def tokenize(text,terms,stopwords):
 text=unicodedata.normalize('NFKC',text).lower();ordered=sorted(terms,key=lambda t:(-len(t),t));stop=set(stopwords);tokens=[];unknown=0;stopped=0;i=0
 while i<len(text):
  match=next((term for term in ordered if text.startswith(term,i)),None)
  if match:
   if match in stop:stopped+=1
   else:tokens.append(match)
   i+=len(match)
  else:
   if text[i].isalnum():unknown+=1
   i+=1
 return {'tokens':tokens,'counts':dict(Counter(tokens)),'unknown_characters':unknown,'stopword_matches':stopped}
