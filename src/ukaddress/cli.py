import argparse, json
from .parser import parse, parse_with_probabilities, tag
from .postcode import normalize_postcode, extract_outcode, get_post_town, get_county
from .models import resolve_model_path, download_model, list_installed_models, set_default_model


def main(argv=None):
    parser = argparse.ArgumentParser(prog="ukaddress-ner", description="UK address NER (CRFsuite)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_parse = sub.add_parser("parse", help="Tag an address")
    p_parse.add_argument("text")
    p_parse.add_argument("--model", help=".crfsuite path (optional; will auto-resolve if omitted)")
    p_parse.add_argument("--probs", action="store_true", help="Include probabilities")

    p_tag = sub.add_parser("tag", help="Return dict of components")
    p_tag.add_argument("text")
    p_tag.add_argument("--model")

    p_pc = sub.add_parser("postcode", help="Postcode utilities")
    p_pc.add_argument("pc")
    p_pc.add_argument("--county", action="store_true")
    p_pc.add_argument("--town", action="store_true")

    p_models = sub.add_parser("models", help="Manage models")
    g = p_models.add_subparsers(dest="mcmd", required=True)
    g.add_parser("list", help="List installed models")
    g.add_parser("resolve", help="Print the model path that would be used")

    p_set = g.add_parser("set-default", help="Set default model (path or installed name)")
    p_set.add_argument("path_or_name")

    p_dl = g.add_parser("download", help="Download a model to user cache")
    p_dl.add_argument("name")
    p_dl.add_argument("url")
    p_dl.add_argument("--sha256")

    args = parser.parse_args(argv)

    if args.cmd == "parse":
        model = resolve_model_path(args.model) if not args.model else resolve_model_path(args.model)
        out = parse_with_probabilities(args.text, model) if args.probs else parse(args.text, model)
        print(json.dumps(out, ensure_ascii=False, indent=2));
        return 0

    if args.cmd == "tag":
        model = resolve_model_path(args.model) if not args.model else resolve_model_path(args.model)
        print(json.dumps(tag(args.text, model), ensure_ascii=False, indent=2));
        return 0

    if args.cmd == "postcode":
        out = {"normalized": normalize_postcode(args.pc), "outcode": extract_outcode(args.pc)}
        if args.town:
            try:
                out["post_town"] = get_post_town(args.pc)
            except Exception:
                out["post_town"] = None
        if args.county:
            out["county"] = get_county(args.pc)
        print(json.dumps(out, ensure_ascii=False, indent=2));
        return 0

    if args.cmd == "models":
        if args.mcmd == "list":
            items = [{"name": m.name, "path": str(m.path)} for m in list_installed_models()]
            print(json.dumps(items, indent=2));
            return 0
        if args.mcmd == "resolve":
            print(str(resolve_model_path()));
            return 0
        if args.mcmd == "set-default":
            print(str(set_default_model(args.path_or_name)));
            return 0
        if args.mcmd == "download":
            path = download_model(args.name, args.url, sha256=args.sha256)
            print(str(path));
            return 0

    parser.print_help();
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
