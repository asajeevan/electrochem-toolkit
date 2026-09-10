"""Explicit source-context linkage; never infer chronological or technique correspondence."""
import hashlib,json
from .text import parse,Options,ImportFailure
from electrochem.models import Project,Source,MetadataRevision

def link_settings(project:Project,blobs:dict[str,bytes],data:bytes,name:str,*,experiment_ids:tuple[str,...],evidence:str,options:Options=Options()):
    project=Project.model_validate_json(project.model_dump_json())
    if not isinstance(evidence,str) or not evidence.strip():raise ImportFailure('link_evidence_required','Explain why this settings file belongs to the selected experiments')
    if not experiment_ids or len(set(experiment_ids))!=len(experiment_ids) or not set(experiment_ids)<={e.id for e in project.experiments}:
        raise ImportFailure('link_targets','Explicit existing experiment IDs required')
    if set(blobs)!={s.sha256 for s in project.sources}:raise ImportFailure('link_source_set','Existing source payloads must match project sources')
    for s in project.sources:
        if len(blobs[s.sha256])!=s.byte_size or hashlib.sha256(blobs[s.sha256]).hexdigest()!=s.sha256:raise ImportFailure('link_source_hash','Existing source payload is corrupt')
    parsed=parse(data,name,options)
    if parsed.source.format!='mps':raise ImportFailure('settings_required','Only a recognized MPS settings file can be linked here')
    payload=json.dumps({'version':'0.1.0','relation':'settings_context_for','experiment_ids':experiment_ids,'evidence':evidence,
      'settings':json.loads(parsed.model_dump_json()),'interpretation':'No chronology, technique parameters, mass or area inferred'},sort_keys=True,ensure_ascii=False).encode()
    digest=hashlib.sha256(payload).hexdigest()
    context=Source(sha256=digest,byte_size=len(payload),original_name=name+'.link.json',format='other')
    sources=list(project.sources);out=dict(blobs)
    for src,b in [(parsed.source,data),(context,payload)]:
        if src.sha256 not in out:sources.append(src);out[src.sha256]=b
    if len(sources)==len(project.sources):return project,out
    current=next(m for m in project.metadata if m.id==project.current_metadata_revision)
    revision=MetadataRevision(id='link-'+digest,parent_id=current.id,reason='Explicit settings context linked; '+evidence,entries=current.entries)
    return project.revised(sources=tuple(sources),metadata=project.metadata+(revision,),current_metadata_revision=revision.id),out
