"""Pinned optional Galvani adapter. No third-party parser code is copied here.
Binary field bytes are authoritative; decoded labels are backend interpretations.
"""
from pathlib import Path
from typing import Annotated,Literal
from pydantic import Field
import hashlib,importlib,json,tempfile
from .text import ImportFailure,Mapping,numeric
from electrochem.models import (Record,Source,Column,RowRef,RawRow,Channel,Observation,
    Experiment,Interval,MetadataRevision,Project,Provenance)
VERSION='0.1.0'
COMMIT='d4a5f444b16eae57d2edfad6df774ead95c92fd6'
BACKEND_HASHES={'BioLogic.py':'4a2e5bf35ad101c519b90175a599cc16c27893707cbd20b54dedee2775ebfb1d',
 '__init__.py':'56c3b67156f7ad4cac929b33a0f2552981b7d272864fe714f395218d5844f041'}
MAX_BYTES=256*1024*1024  # raised from the 10 MiB P03 profile; a 100-cycle GCPL export is 30 MB+
class NativeField(Record):
    backend_label:str
    dtype:str
    offset:Annotated[int,Field(ge=0)]
    width:Annotated[int,Field(gt=0)]
    interpreted_unit:str|None
class NativeModule(Record):
    payload_offset:Annotated[int,Field(ge=0)]
    payload_length:Annotated[int,Field(ge=0)]
    version:int
    name_hex:str
    longname_hex:str
    date_hex:str
    payload_sha256:str
class NativeRow(Record):
    byte_offset:Annotated[int,Field(ge=0)]
    field_hex:tuple[str,...]
    decoded_text:tuple[str,...]
class NativeFlag(Record):
    backend_label:str
    mask:int
    dtype:str
class NativeTable(Record):
    adapter_version:Literal['0.1.0']='0.1.0'
    backend_commit:Literal['d4a5f444b16eae57d2edfad6df774ead95c92fd6']=COMMIT
    numpy_version:str
    source:Source
    modules:tuple[NativeModule,...]
    fields:tuple[NativeField,...]
    flags:tuple[NativeFlag,...]
    encoded_column_ids:tuple[int,...]
    data_module_version:int
    record_width:int
    data_offset:int
    rows:tuple[NativeRow,...]
    backend_loop_indices:tuple[int,...]|None

def backend():
    if not __debug__:raise ImportFailure('optimized_python_unsupported','Pinned reader uses assertions; run Python without -O')
    try:mod=importlib.import_module('galvani.BioLogic');np=importlib.import_module('numpy')
    except ImportError as exc:raise ImportFailure('native_dependency_missing','Install requirements-native.txt (pip install -r requirements-native.txt) in the research environment') from exc
    root=Path(mod.__file__).parent
    for name,digest in BACKEND_HASHES.items():
        if hashlib.sha256((root/name).read_bytes().replace(b'\r\n',b'\n')).hexdigest()!=digest:  # line endings normalised: Git on Windows checks out CRLF
            raise ImportFailure('native_backend_unverified','Reader source differs from the evaluated revision; review before updating pin')
    if np.__version__!='2.3.5':raise ImportFailure('native_numpy_unverified','This adapter was tested with NumPy 2.3.5')
    return mod,np

def inspect_native(data:bytes,name:str)->NativeTable:
    if not isinstance(data,bytes):raise TypeError('Original binary bytes required')
    if len(data)>MAX_BYTES:raise ImportFailure('size_limit','Native input exceeds 256 MiB')
    mod,np=backend()
    if not data.startswith(mod.MPR_MAGIC):raise ImportFailure('native_signature','Not a supported MPR signature')
    # Fixed private filename prevents directory-dependent LOOP/MPL lookup and backend BytesIO fallback bugs.
    try:
        with tempfile.TemporaryDirectory(prefix='eclab-native-') as d:
            p=Path(d)/'source.mpr';p.write_bytes(data)
            obj=mod.MPRfile(str(p),error_on_unknown_column=True)
    except (ValueError,IOError,AssertionError,NotImplementedError,IndexError,UnboundLocalError,RuntimeError) as exc:
        raise ImportFailure('native_decode_failed',type(exc).__name__+': '+str(exc)) from exc
    array=obj.data
    if len(array)>5_000_000 or len(array.dtype.names)>128:raise ImportFailure('native_table_limit','Record/field count outside evaluated in-memory limits')
    declared=int(obj.npts.item())
    if declared!=len(array):raise ImportFailure('native_record_count','Declared record count differs from decoded count')
    modules=[];previous_end=0
    for m in obj.modules:
        off,length=int(m['offset']),int(m['length'])
        if off<previous_end or off+length>len(data) or data[off:off+length]!=m['data']:
            raise ImportFailure('native_module_bounds','Decoded module does not match original bytes')
        previous_end=off+length
        modules.append(NativeModule(payload_offset=off,payload_length=length,version=int(m['version']),
          name_hex=bytes(m['shortname']).hex(),longname_hex=bytes(m['longname']).hex(),date_hex=bytes(m['date']).hex(),
          payload_sha256=hashlib.sha256(m['data']).hexdigest()))
    if previous_end!=len(data):raise ImportFailure('native_trailing_data','Not all input bytes belong to decoded modules')
    dm=[m for m in obj.modules if m['shortname']==b'VMP data  ']
    if len(dm)!=1:raise ImportFailure('native_data_modules','Exactly one data module required')
    offset=int(dm[0]['offset'])+len(dm[0]['data'])-array.nbytes
    if data[offset:offset+array.nbytes]!=array.tobytes():raise ImportFailure('native_record_bytes','Array does not reproduce source record bytes')
    fields=[];cursor=0
    for label in array.dtype.names:
        dtype,field_offset=array.dtype.fields[label][:2]
        if dtype.kind not in 'fiub' or dtype.shape or int(field_offset)!=cursor:
            raise ImportFailure('native_dtype_unsupported','Only contiguous scalar numerical fields are accepted')
        fields.append(NativeField(backend_label=label,dtype=dtype.str,offset=int(field_offset),width=dtype.itemsize,
            interpreted_unit=label.rsplit('/',1)[1] if '/' in label else None))
        cursor+=dtype.itemsize
    if cursor!=array.dtype.itemsize:raise ImportFailure('native_record_padding','Unaccounted record padding')
    rows=[]
    for k,row in enumerate(array):
        pos=offset+k*array.dtype.itemsize
        rows.append(NativeRow(byte_offset=pos,field_hex=tuple(data[pos+f.offset:pos+f.offset+f.width].hex() for f in fields),
            decoded_text=tuple(str(row[f.backend_label].item()) for f in fields)))
    return NativeTable(numpy_version=np.__version__,source=Source(sha256=hashlib.sha256(data).hexdigest(),byte_size=len(data),original_name=name,format='mpr',
        columns=tuple(Column(original_name=f'encoded_field_{i}',original_unit=None) for i in range(len(fields)))),
        modules=tuple(modules),fields=tuple(fields),flags=tuple(NativeFlag(backend_label=n,mask=int(mask),dtype=np.dtype(dtype).str) for n,(mask,dtype) in obj.flags_dict.items()),
        encoded_column_ids=tuple(int(v) for v in obj.cols),data_module_version=int(obj.version),record_width=array.dtype.itemsize,data_offset=offset,rows=tuple(rows),
        backend_loop_indices=None if obj.loop_index is None else tuple(int(v) for v in obj.loop_index))

def project_from_native(table:NativeTable,data:bytes,mapping:Mapping)->tuple[Project,dict[str,bytes]]:
    mapping=Mapping.model_validate_json(mapping.model_dump_json())
    if inspect_native(data,table.source.original_name)!=table:raise ImportFailure('native_source_mismatch','Decoded table does not reproduce original input')
    selections=[mapping.time,mapping.current,mapping.potential,mapping.native_step,mapping.native_cycle]
    indices=[i for i in selections if i is not None]
    if len(indices)!=len(set(indices)) or any(i>=len(table.fields) for i in indices):raise ImportFailure('column_mapping','Selected native field indices must be distinct and present')
    if mapping.current is None and mapping.current_multiplier is not None:raise ImportFailure('column_mapping','Current convention without channel')
    if mapping.potential is None and (mapping.potential_role!='unresolved' or mapping.positive_node or mapping.negative_node or mapping.reference):raise ImportFailure('column_mapping','Potential convention without channel')
    prov=Provenance(origin='user',evidence=mapping.evidence,revision='native-review-1')
    channels=[]
    for cid,idx,quantity in [('time',mapping.time,'time'),('current',mapping.current,'current'),('potential',mapping.potential,'potential')]:
        if idx is None:continue
        field=table.fields[idx]
        if not field.interpreted_unit:raise ImportFailure('missing_unit','No backend unit for selected field')
        extra={}
        if quantity=='current':extra={'current_polarity':mapping.current_multiplier}
        if quantity=='potential':extra={'potential_role':mapping.potential_role,'positive_node':mapping.positive_node,'negative_node':mapping.negative_node,'reference':mapping.reference}
        channels.append(Channel(id=cid,source_hash=table.source.sha256,column_index=idx,quantity=quantity,input_unit=field.interpreted_unit,provenance=prov,**extra))
    refs=tuple(RowRef(source_hash=table.source.sha256,record_index=k) for k in range(len(table.rows)))
    raw=tuple(RawRow(ref=ref,tokens=row.field_hex) for ref,row in zip(refs,table.rows))
    obs=tuple(Observation(ref=ref,experiment_id='imported-experiment',acquisition_order=k,block_id='unreviewed',
        samples=tuple(numeric(row.decoded_text[ch.column_index],ch,'.') for ch in channels),
        native_step=row.decoded_text[mapping.native_step] if mapping.native_step is not None else None,
        native_cycle=row.decoded_text[mapping.native_cycle] if mapping.native_cycle is not None else None)
        for k,(ref,row) in enumerate(zip(refs,table.rows)))
    context=json.dumps({'native_table':json.loads(table.model_dump_json()),'mapping':json.loads(mapping.model_dump_json()),
        'raw_row_representation':'hexadecimal original binary field bytes, not textual observations',
        'label_and_unit_origin':'pinned backend interpretation; original encoded IDs retained in native_table',
        'external_sidecars':'never implicitly loaded','timestamps':'no absolute time assigned','settings':'module bytes preserved, not interpreted'},sort_keys=True,allow_nan=False).encode()
    digest=hashlib.sha256(context).hexdigest()
    source=Source(sha256=digest,byte_size=len(context),original_name=table.source.original_name+'.native-import.json',format='other')
    intervals=tuple(Interval(id=f'edge-{k}',left=refs[k],right=refs[k+1],status='unresolved',reconstruction='none',reason='Native acquisition and step support await review',provenance=prov) for k in range(len(refs)-1))
    project=Project(id='native-'+table.source.sha256[:16],sources=(table.source,source),raw_rows=raw,channels=tuple(channels),observations=obs,
      experiments=(Experiment(id='imported-experiment',cell_id='unresolved-cell',configuration=mapping.configuration,technique=mapping.technique,time_channel='time',
      current_channel='current' if mapping.current is not None else None,voltage_channel='potential' if mapping.potential is not None else None,
      passive_current_confirmed=mapping.passive_current_confirmed,convention_provenance=prov if mapping.passive_current_confirmed else None,clock_tolerance_s=0.),),
      intervals=intervals,metadata=(MetadataRevision(id='native-import-1',reason='Binary metadata preserved without inference',entries=()),),current_metadata_revision='native-import-1')
    return project,{table.source.sha256:data,digest:context}
