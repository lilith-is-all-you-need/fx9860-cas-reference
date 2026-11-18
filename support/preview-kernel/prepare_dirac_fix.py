"""Apply a pinned, isolated repair; never change the accepted source/archive."""
from pathlib import Path
import argparse
import difflib
import hashlib
import json

BASE_SHA256 = "18c8748fb185f6aaf32b41ed558a117ffdfc044fe539d749caaa0a1906f1f9a5"

HELPER = r'''  // A polynomial test weight is smooth at every finite real support point.
  // Keep derivative distributions conservative instead of evaluating a cusp
  // or pole as though the required derivative existed.
  static bool dirac_polynomial_weight(const gen & g,const gen & x,GIAC_CONTEXT){
    control_c();
    if (g==x)
      return true;
    if (!depend(g,*x._IDNTptr))
      return !is_undef(g) && !is_inf(g);
    if (g.type==_FRAC)
      return !depend(g._FRACptr->den,*x._IDNTptr) &&
        dirac_polynomial_weight(g._FRACptr->num,x,contextptr);
    if (g.type!=_SYMB)
      return false;
    const unary_function_ptr & u=g._SYMBptr->sommet;
    const gen & f=g._SYMBptr->feuille;
    if (u==at_neg)
      return dirac_polynomial_weight(f,x,contextptr);
    if (u==at_pow && f.type==_VECT && f._VECTptr->size()==2 &&
        f._VECTptr->back().type==_INT_ && f._VECTptr->back().val>=0)
      return dirac_polynomial_weight(f._VECTptr->front(),x,contextptr);
    if ((u==at_plus || u==at_prod) && f.type==_VECT){
      for (const_iterateur it=f._VECTptr->begin();it!=f._VECTptr->end();++it){
        if (!dirac_polynomial_weight(*it,x,contextptr))
          return false;
      }
      return true;
    }
    return false;
  }

'''

OLD = r'''      gen heav=v.front()._SYMBptr->feuille;
      if (heav.type==_VECT && heav._VECTptr->size()==2 && heav._VECTptr->back().type==_INT_ ){
	int diracorder=heav._VECTptr->back().val;
	if (diracorder<0){
	  *logptr(contextptr) << gettext("Negative second Dirac argument") << endl;
	  return false;
	}
	A=derive(A,x,diracorder,contextptr);
	if (is_undef(A))
	  return false;
	if (diracorder%2)
	  A=-A;
	heav=heav._VECTptr->front();
      }
      if (!is_linear_wrt(heav,x,a0,b0,contextptr) || is_zero(a0))
	return false;
      if (!intgab(B,x,a,b,res,contextptr))
	return false;
      gen c=-b0/a0;
      if (ck_is_greater(c,a,contextptr) && ck_is_greater(b,c,contextptr))
	res += quotesubst(A,x,c,contextptr);
      else
	*logptr(contextptr) << gettext("Warning, Dirac function outside summation interval") << endl;
      return true;
'''

NEW = r'''      gen heav=v.front()._SYMBptr->feuille;
      int diracorder=0;
      if (heav.type==_VECT && heav._VECTptr->size()==2 && heav._VECTptr->back().type==_INT_ ){
	diracorder=heav._VECTptr->back().val;
	if (diracorder<0){
	  *logptr(contextptr) << gettext("Negative second Dirac argument") << endl;
	  return false;
	}
	heav=heav._VECTptr->front();
      }
      if (!is_linear_wrt(heav,x,a0,b0,contextptr) || is_zero(a0))
	return false;
      if (!is_real(a0,contextptr) || !is_real(b0,contextptr) ||
          is_inf(a0) || is_inf(b0)){
	res=symb_integrate(g0,x,a,b);
	return true;
      }
      const bool positive=is_strictly_greater(a0,0,contextptr);
      const bool negative=is_strictly_greater(0,a0,contextptr);
      if (!positive && !negative){
	res=symb_integrate(g0,x,a,b);
	return true;
      }
      gen c=-b0/a0;
      const bool endpoint=c==a || c==b;
      const bool inside=is_strictly_greater(c,a,contextptr) &&
        is_strictly_greater(b,c,contextptr);
      const bool outside=is_strictly_greater(a,c,contextptr) ||
        is_strictly_greater(c,b,contextptr);
      // Preserve the existing full-mass endpoint convention for delta itself.
      // Derivative distributions require an interior, smooth test function;
      // a closed-interval endpoint has no canonical value without a convention.
      if ((!inside && !endpoint && !outside) ||
          (diracorder && (endpoint || !dirac_polynomial_weight(A,x,contextptr)))){
	res=symb_integrate(g0,x,a,b);
	return true;
      }
      if (!intgab(B,x,a,b,res,contextptr))
	return false;
      if (outside)
	return true;
      if (diracorder){
	A=derive(A,x,diracorder,contextptr);
	if (is_undef(A))
	  return false;
	if (diracorder%2)
	  A=-A;
      }
      gen weight=ratnormal(quotesubst(A,x,c,contextptr),contextptr);
      if (is_undef(weight) || is_inf(weight)){
	res=symb_integrate(g0,x,a,b);
	return true;
      }
      // delta^(n)(a*x+b) acts as (-1)^n*f^(n)(-b/a)/(|a|*a^n).
      res += weight/((positive?a0:-a0)*pow(a0,diracorder,contextptr));
      return true;
'''


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    data = args.source.read_bytes()
    if hashlib.sha256(data).hexdigest() != BASE_SHA256:
        raise SystemExit("The source is not the reviewed clean kintgab.cc")
    text = data.decode("latin1")
    anchor = "  static bool intgab(const gen & g0,const gen & x,const gen & a,const gen & b,gen & res,bool nonrecursive,GIAC_CONTEXT){"
    if text.count(anchor) != 1 or text.count(OLD) != 1:
        raise SystemExit("Expected exactly one reviewed helper/Dirac branch")
    updated = text.replace(anchor, HELPER + anchor).replace(OLD, NEW)
    args.output.mkdir(parents=True, exist_ok=True)
    target = args.output / "kintgab.cc"
    if target.resolve() == args.source.resolve():
        raise SystemExit("Refusing to overwrite the accepted source")
    target.write_bytes(updated.encode("latin1"))
    (args.output / "dirac-scaling.patch").write_text("".join(difflib.unified_diff(
        text.splitlines(True), updated.splitlines(True),
        fromfile="accepted/kintgab.cc", tofile="preview/kintgab.cc")), encoding="utf-8")
    (args.output / "source-binding.json").write_text(json.dumps({
        "source": str(args.source), "source_sha256": BASE_SHA256,
        "candidate": str(target),
        "candidate_sha256": hashlib.sha256(target.read_bytes()).hexdigest(),
        "scope": "Real, nonzero linear Dirac scaling; polynomial weights for derivative distributions; explicit refusal of unknown sign/support and derivative endpoints.",
        "accepted_source_unchanged": hashlib.sha256(args.source.read_bytes()).hexdigest() == BASE_SHA256,
    }, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
