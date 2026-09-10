"""python -m eclab_import FILE [--mapping MAP.json --output NEW.ecproj]"""
from pathlib import Path
import sys,argparse,json
# Portable source-bundle execution; installed core can also be imported normally.
from .text import parse,project_from_text,Options,Mapping,MAX_BYTES
from electrochem.archive import save

def main():
    ap=argparse.ArgumentParser(description='Review EC/BT-Lab text; no automatic integration or file modification')
    ap.add_argument('file',type=Path)
    ap.add_argument('--encoding',choices=['auto_utf8','utf-8','utf-8-sig','cp1252','iso-8859-1'],default='auto_utf8')
    ap.add_argument('--decimal',choices=['.',','],default='.')
    ap.add_argument('--headerless',action='store_true')
    ap.add_argument('--missing-terminal-empty-field',action='store_true')
    ap.add_argument('--native',action='store_true',help='Use the pinned optional MPR adapter')
    ap.add_argument('--settings',type=Path)
    ap.add_argument('--settings-encoding',choices=['auto_utf8','cp1252','iso-8859-1'],default='auto_utf8')
    ap.add_argument('--link-evidence')
    ap.add_argument('--mapping',type=Path)
    ap.add_argument('--output',type=Path)
    args=ap.parse_args()
    if bool(args.mapping)!=bool(args.output):ap.error('--mapping and --output must be supplied together')
    if args.settings and (not args.mapping or not args.link_evidence):ap.error('--settings requires --mapping, --output and --link-evidence')
    if args.link_evidence and not args.settings:ap.error('--link-evidence requires --settings')
    try:
        with args.file.open('rb') as f:data=f.read(MAX_BYTES+1)
        if args.native:
            from .native import inspect_native,project_from_native
            parsed=inspect_native(data,args.file.name)
            summary={'adapter_version':parsed.adapter_version,'source_sha256':parsed.source.sha256,'format':'mpr',
                'rows':len(parsed.rows),'backend_fields':[{'index':i,**f.model_dump()} for i,f in enumerate(parsed.fields)],
                'encoded_column_ids':parsed.encoded_column_ids,'modules':[m.model_dump() for m in parsed.modules],
                'status':'review_required; labels are backend interpretations; intervals unresolved'}
            project_builder=project_from_native
        else:
            parsed=parse(data,args.file.name,Options(encoding=args.encoding,decimal=args.decimal,headerless=args.headerless,missing_terminal_empty_field=args.missing_terminal_empty_field))
            summary={'parser_version':parsed.parser_version,'source_sha256':parsed.source.sha256,'format':parsed.source.format,'encoding':parsed.resolved_encoding,
              'rows':len(parsed.rows),'column_line':parsed.column_line,'columns':[{'index':i,**c.model_dump()} for i,c in enumerate(parsed.source.columns)],
              'diagnostics':list(parsed.diagnostics),'status':'review_required; no intervals qualified for integration'}
            project_builder=project_from_text
        if args.mapping:
            mapping=Mapping.model_validate_json(args.mapping.read_bytes());p,blobs=project_builder(parsed,data,mapping)
            if args.settings:
                from .linkage import link_settings
                with args.settings.open('rb') as handle:settings=handle.read(MAX_BYTES+1)
                p,blobs=link_settings(p,blobs,settings,args.settings.name,experiment_ids=tuple(e.id for e in p.experiments),
                    evidence=args.link_evidence,options=Options(encoding=args.settings_encoding))
            save(p,blobs,args.output);summary['saved_project']=str(args.output)
        print(json.dumps(summary,indent=2,ensure_ascii=False))
    except (ValueError,OSError) as exc:
        print(str(exc),file=sys.stderr);return 2
    return 0
if __name__=='__main__':raise SystemExit(main())
