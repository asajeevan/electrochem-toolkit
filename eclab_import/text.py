"""Lossless source retention and explicit normalization for tab-delimited EC-Lab text.
Layout contract is in docs/handoffs/P03_text_import_README.md. No binary decoding or analysis here.
"""
from typing import Literal, Annotated
from pathlib import Path
import hashlib,json,re
from decimal import Decimal,InvalidOperation
from pydantic import Field
from electrochem.units import unit as unit_definition
from electrochem.models import (Record,Source,Column,RawRow,RowRef,Channel,Observation,Sample,
    Experiment,Interval,MetadataRevision,Project,Provenance,canonical_bytes,normalize)
VERSION='0.1.0'
MAX_BYTES=10*1024*1024
class ImportFailure(ValueError):
    def __init__(self,code,message,line=None):
        self.code,self.line=code,line
        super().__init__(f'{code}'+(f' at line {line}' if line else '')+': '+message)
class Options(Record):
    encoding: Literal['auto_utf8','utf-8','utf-8-sig','cp1252','iso-8859-1']='auto_utf8'
    decimal: Literal['.',',']='.'
    headerless: bool=False
    missing_terminal_empty_field: bool=False
class Line(Record):
    number: Annotated[int,Field(ge=1)]
    text: str
class TextRow(Record):
    line_number: Annotated[int,Field(ge=1)]
    fields: tuple[str,...]
class Parsed(Record):
    parser_version: Literal['0.1.0']='0.1.0'
    source: Source
    options: Options
    resolved_encoding: str
    signature: str
    header: tuple[Line,...]
    column_line: int|None
    rows: tuple[TextRow,...]
    diagnostics: tuple[str,...]
class Mapping(Record):
    time: Annotated[int,Field(ge=0)]
    current: Annotated[int,Field(ge=0)]|None=None
    potential: Annotated[int,Field(ge=0)]|None=None
    native_step: Annotated[int,Field(ge=0)]|None=None
    native_cycle: Annotated[int,Field(ge=0)]|None=None
    current_multiplier: Literal[-1,1]|None=None
    potential_role: Literal['terminal','electrode','unresolved']='unresolved'
    positive_node: str|None=None
    negative_node: str|None=None
    reference: str|None=None
    configuration: Literal['full_cell','metal_half_cell','three_electrode','symmetric','blocking','unknown']='unknown'
    passive_current_confirmed: bool=False
    technique: str='unresolved'
    evidence: Annotated[str,Field(min_length=1)]

def parse(data:bytes,name:str,options:Options=Options())->Parsed:
    if not isinstance(data,bytes):raise TypeError('Input must be original bytes')
    if len(data)>MAX_BYTES:raise ImportFailure('size_limit','P03 text limit is 10 MiB')
    options=Options.model_validate_json(options.model_dump_json())
    if data.startswith(b'BIO-LOGIC MODULAR FILE') or Path(name).suffix.lower()=='.mpr':
        raise ImportFailure('native_mpr_not_enabled','Retain native file; a validated native adapter is still required')
    encoding='utf-8-sig' if options.encoding=='auto_utf8' else options.encoding
    try:text=data.decode(encoding,errors='strict')
    except UnicodeDecodeError as exc:raise ImportFailure('encoding_required','Choose a verified encoding; no replacement decoding') from exc
    # split only physical CR/LF lines; do not treat arbitrary Unicode control characters as row boundaries.
    lines=re.split(r'\r\n|\n|\r',text)
    if lines and lines[-1]=='':lines.pop()
    if not lines or not lines[0]:raise ImportFailure('empty_file','No signature or table')
    if '\x00' in text:raise ImportFailure('binary_or_nul','NUL is not supported in this text profile')
    signature=lines[0];diagnostics=[]
    is_settings=signature in ['EC-LAB SETTING FILE','BT-LAB SETTING FILE']
    if is_settings:
        if options.headerless:raise ImportFailure('settings_not_measurements','Settings are context only')
        return Parsed(source=Source(sha256=hashlib.sha256(data).hexdigest(),byte_size=len(data),original_name=name,format='mps'),
          options=options,resolved_encoding=encoding,signature=signature,header=tuple(Line(number=i+1,text=s) for i,s in enumerate(lines)),
          column_line=None,rows=(),diagnostics=('settings_context_only',))
    if Path(name).suffix.lower()=='.mps':raise ImportFailure('settings_signature','Unrecognized settings signature')
    if options.headerless:
        if signature in ['EC-Lab ASCII FILE','BT-Lab ASCII FILE']:raise ImportFailure('header_mode_conflict','Signed export cannot be parsed as headerless')
        col_index=0;diagnostics.append('headerless_explicitly_selected')
    else:
        if signature not in ['EC-Lab ASCII FILE','BT-Lab ASCII FILE']:raise ImportFailure('signature_required','Headerless text requires explicit selection')
        match=re.fullmatch(r'Nb header lines\s*:\s*([0-9]+)\s*',lines[1] if len(lines)>1 else '')
        if not match:raise ImportFailure('header_count','Missing or malformed header count',2)
        count=int(match[1])
        if count<3 or count>len(lines):raise ImportFailure('header_count','Header count outside file bounds',2)
        col_index=count-1
    names=lines[col_index].split('\t')
    if len(names)<2:raise ImportFailure('delimiter','This profile requires a tab-separated column line',col_index+1)
    def unit_suffix(n):return n.rsplit('/',1)[1] if '/' in n else None
    columns=tuple(Column(original_name=n,original_unit=unit_suffix(n)) for n in names)
    rows=[]
    for i,line in enumerate(lines[col_index+1:],col_index+2):
        fields=tuple(line.split('\t'))
        if len(fields)!=len(names):
            if options.missing_terminal_empty_field and names[-1]=='' and len(fields)==len(names)-1:
                diagnostics.append(f'absent_terminal_empty_field:line={i}')
            else:raise ImportFailure('row_width',f'Expected {len(names)} fields, received {len(fields)}; no row skipped or padded',i)
        rows.append(TextRow(line_number=i,fields=fields))
    if not rows:diagnostics.append('no_observations')
    return Parsed(source=Source(sha256=hashlib.sha256(data).hexdigest(),byte_size=len(data),original_name=name,format='mpt',columns=columns),
      options=options,resolved_encoding=encoding,signature=signature,header=tuple(Line(number=i+1,text=s) for i,s in enumerate(lines[:col_index])),
      column_line=col_index+1,rows=tuple(rows),diagnostics=tuple(diagnostics))

def numeric(token:str|None,channel:Channel,decimal:str)->Sample:
    if token is None or token.strip()=='':return normalize(None,channel,missing_reason='Empty or absent exported field')
    value=token.strip();sep=re.escape(decimal)
    # No grouping separators, automatic decimal replacement, NaN coercion, or timestamp guessing.
    pattern=rf'[+-]?(?:[0-9]+(?:{sep}[0-9]*)?|{sep}[0-9]+)(?:[eE][+-]?[0-9]+)?'
    if not re.fullmatch(pattern,value):return Sample(channel_id=channel.id,value_si=None,validity='invalid',reason='Unsupported numeric token or decimal convention')
    try:
        exact=Decimal(value.replace(decimal,'.'))
        scalar=float(exact)
        if scalar==0 and exact!=0:raise ValueError('Binary float underflow')
        sample=normalize(scalar,channel)
        if scalar!=0 and sample.value_si==0 and unit_definition(channel.input_unit).offset==0:
            raise ValueError('SI conversion underflow')
        return sample
    except (InvalidOperation,ValueError,OverflowError):
        return Sample(channel_id=channel.id,value_si=None,validity='invalid',reason='Value is not finite/representable in normalized SI')

def project_from_text(parsed:Parsed,data:bytes,mapping:Mapping)->tuple[Project,dict[str,bytes]]:
    parsed=Parsed.model_validate_json(parsed.model_dump_json());mapping=Mapping.model_validate_json(mapping.model_dump_json())
    # Reparse exact bytes: caller cannot replace headers/rows while preserving an old source hash.
    if parse(data,parsed.source.original_name,parsed.options)!=parsed:raise ImportFailure('source_mismatch','Parsed records do not reproduce source bytes')
    if parsed.source.format=='mps':raise ImportFailure('settings_not_measurements','MPS cannot replace measurement data')
    indices=[v for v in [mapping.time,mapping.current,mapping.potential,mapping.native_step,mapping.native_cycle] if v is not None]
    if len(set(indices))!=len(indices) or any(v>=len(parsed.source.columns) for v in indices):raise ImportFailure('column_mapping','Indices must be distinct and present')
    if mapping.current is None and mapping.current_multiplier is not None:raise ImportFailure('column_mapping','Current convention without current channel')
    if mapping.potential is None and (mapping.potential_role!='unresolved' or mapping.positive_node or mapping.negative_node or mapping.reference):raise ImportFailure('column_mapping','Potential convention without potential channel')
    prov=Provenance(origin='user',evidence=mapping.evidence,revision='import-review-1')
    channels=[]
    for cid,idx,quantity in [('time',mapping.time,'time'),('current',mapping.current,'current'),('potential',mapping.potential,'potential')]:
        if idx is None:continue
        unit=parsed.source.columns[idx].original_unit
        if not unit:raise ImportFailure('missing_unit',f'Column {idx} has no explicit unit')
        extra={}
        if quantity=='current':extra={'current_polarity':mapping.current_multiplier}
        if quantity=='potential':extra={'potential_role':mapping.potential_role,'positive_node':mapping.positive_node,'negative_node':mapping.negative_node,'reference':mapping.reference}
        channels.append(Channel(id=cid,source_hash=parsed.source.sha256,column_index=idx,quantity=quantity,input_unit=unit,provenance=prov,**extra))
    refs=tuple(RowRef(source_hash=parsed.source.sha256,record_index=i) for i in range(len(parsed.rows)))
    raw=[];obs=[]
    for i,row in enumerate(parsed.rows):
        # Only explicitly accepted absent terminal empty fields become None. Exact fields remain in Parsed.
        fields=row.fields+(None,)*(len(parsed.source.columns)-len(row.fields))
        raw.append(RawRow(ref=refs[i],tokens=fields))
        obs.append(Observation(ref=refs[i],experiment_id='imported-experiment',acquisition_order=i,block_id='unreviewed',
          samples=tuple(numeric(fields[ch.column_index],ch,parsed.options.decimal) for ch in channels),
          native_step=fields[mapping.native_step] if mapping.native_step is not None else None,
          native_cycle=fields[mapping.native_cycle] if mapping.native_cycle is not None else None))
    context=json.dumps({'parser_version':VERSION,'parsed':json.loads(parsed.model_dump_json()),'mapping':json.loads(mapping.model_dump_json()),
      'interval_policy':'all unresolved until P04 review','absolute_time_policy':'unparsed; no timezone inferred'},sort_keys=True,ensure_ascii=False,allow_nan=False).encode()
    context_hash=hashlib.sha256(context).hexdigest()
    context_source=Source(sha256=context_hash,byte_size=len(context),original_name=parsed.source.original_name+'.import.json',format='other')
    intervals=tuple(Interval(id=f'edge-{i}',left=refs[i],right=refs[i+1],status='unresolved',reason='Acquisition support and step semantics await review',
        reconstruction='none',provenance=Provenance(origin='calculation',evidence='P03 '+VERSION+' conservative import',revision='import-1')) for i in range(len(refs)-1))
    project=Project(id='import-'+parsed.source.sha256[:16],sources=(parsed.source,context_source),raw_rows=tuple(raw),channels=tuple(channels),observations=tuple(obs),
      experiments=(Experiment(id='imported-experiment',cell_id='unresolved-cell',configuration=mapping.configuration,technique=mapping.technique,
      time_channel='time',current_channel='current' if mapping.current is not None else None,voltage_channel='potential' if mapping.potential is not None else None,
      passive_current_confirmed=mapping.passive_current_confirmed,convention_provenance=prov if mapping.passive_current_confirmed else None,clock_tolerance_s=0.),),
      intervals=intervals,metadata=(MetadataRevision(id='import-1',reason='Header metadata retained as unconfirmed context',entries=()),),current_metadata_revision='import-1')
    return project,{parsed.source.sha256:data,context_hash:context}
