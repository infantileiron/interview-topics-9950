import {runLabels} from '../../constants/enums';
export default function StatusBadge({status}:{status:string}){return <span className={'badge '+status}>{runLabels[status]||status}</span>}
