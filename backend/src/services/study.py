from src.models.entities import TopicStudy
from src.utils import repository as repo
from src.utils.identity import new_id,now

def list_studies():return repo.all_rows('studies')
def create(data):
 repo.get('datasets',data.dataset_id);repo.get('lexicons',data.lexicon_id)
 return repo.put('studies',TopicStudy(new_id('study'),data.name,data.dataset_id,data.lexicon_id,data.topic_count,data.max_iter,data.tolerance,data.seed,now()))
