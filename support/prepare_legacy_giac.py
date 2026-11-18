"""Prepare an isolated historical Giac core for the current calculator SDK."""

import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil


EXTERNAL_COMMANDS = {
    'addr', 'fclose', 'fopen', 'fprint', 'read', 'read32', 'write', 'write32',
    'python', 'python_compat', 'python_list', 'xcas',
}


def cas_units(source):
    makefile = (source / 'Makefile').read_text()
    objects = re.search(r'^CAS_OBJS\s*=\s*([^#\n]+)', makefile, re.M)
    if not objects:
        raise ValueError('Expected the historical CAS_OBJS list')
    return [name.removesuffix('.o') + '.cc' for name in objects[1].split()]


def remove_between(change, source, filename, opening, closing):
    contents = (source / filename).read_bytes().decode('latin1')
    start = contents.index(opening)
    end = contents.index(closing, start)
    change(filename, contents[start:end], '')


def write_registry(source):
    names = re.findall(r'^\{"([^"\\]+)",([^,]+),0,(-?\d+),13\},',
                       (source / 'static_lexer.h').read_text(), re.M)
    pointers = re.findall(r'^(at_\w+),', (source / 'static_lexer_.h').read_text(), re.M)
    if len(names) != 720 or len(pointers) != len(names):
        raise ValueError('Expected 720 historical names and aligned operator pointers')
    entries = {}
    for (name, bits, token), pointer in zip(names, pointers):
        if name in EXTERNAL_COMMANDS:
            continue
        if name in ('Heaviside', 'Kronecker'):
            pointer = 'at_' + name
        if not re.fullmatch(r'0\s*(?:\|\s*1)?', bits):
            raise ValueError(f'Unexpected argument flags for {name}')
        entries[name] = (pointer, 256 + (int(token) & 255), '1' in bits)
    entries['expand'] = ('at_expand', 265, False)
    declarations = ''.join(f'extern const unary_function_ptr * const {symbol};\n'
                           for symbol in sorted({symbol for symbol, _, _ in entries.values()}))
    rows = ''.join(f'  {{ {json.dumps(name, ensure_ascii=False)}, &{symbol}, '
                   f'{token}, {str(quoted).lower()} }},\n'
                   for name, (symbol, token, quoted) in sorted(entries.items()))
    (source / 'legacy_lexer_registry.inc').write_text(
        declarations + '''namespace {
struct legacy_builtin {
  const char *name;
  const unary_function_ptr * const *function;
  unsigned short token;
  bool quoted;
};
constexpr legacy_builtin builtin_functions[] = {
''' + rows + '''};
}

int find_legacy_builtin(const char *name,gen &value){
  const auto *end=builtin_functions+sizeof(builtin_functions)/sizeof(builtin_functions[0]);
  const auto *entry=std::lower_bound(builtin_functions,end,name,
      [](const legacy_builtin &candidate,const char *key){
        return strcmp(candidate.name,key)<0;
      });
  if (entry==end || strcmp(entry->name,name))
    return 0;
  value=gen(*entry->function);
  if (entry->quoted)
    value._FUNC_|=1;
  return entry->token;
}
''', encoding='utf-8')
    return entries


def patch_alias_layout(change, source):
    change('gen.h', '    gen(){ *(ulonglong *) this=0;}',
           '    gen():_DOUBLE_val(0.0),reserved(0),subtype(0),type(_INT_) {}')
    change('gen.h', '    gen(double d): type(_DOUBLE_),_DOUBLE_val(d) {};',
           '    gen(double d):_DOUBLE_val(d),reserved(0),subtype(0),type(_DOUBLE_) {}')
    change('gen.h', '''  struct alias_gen {
#ifdef DOUBLEVAL
    longlong value;
#else
    long value ; 
#endif
    unsigned short reserved; // not used 
    signed char subtype;
    unsigned char type;  // see dispatch.h
  };''', '''  struct alignas(double) alias_gen {
    long value;
#if __SIZEOF_POINTER__==4
    unsigned long padding;
#endif
    unsigned short reserved;
    signed char subtype;
    unsigned char type;
  };
  static_assert(sizeof(alias_gen)==sizeof(gen), "ROM gen size mismatch");
  static_assert(alignof(alias_gen)==alignof(gen), "ROM gen alignment mismatch");
  static_assert(offsetof(alias_gen,value)==offsetof(gen,val), "ROM gen payload mismatch");
  static_assert(offsetof(alias_gen,type)==offsetof(gen,type), "ROM gen type mismatch");''')
    text = (source / 'gen.h').read_bytes().decode('latin1')
    first = text.index('#ifdef DOUBLEVAL\n#define define_alias_gen')
    last = text.index('#else // DOUBLEVAL', first)
    change('gen.h', text[first:last], '''#ifdef DOUBLEVAL
#if __SIZEOF_POINTER__==4
#define LEGACY_ALIAS_PAYLOAD(value) long(value),0
#else
#define LEGACY_ALIAS_PAYLOAD(value) long(value)
#endif
#define LEGACY_ALIAS_GEN(type,subtype,value) {LEGACY_ALIAS_PAYLOAD(value),0,subtype,type}
#define define_alias_gen(name,type,subtype,ptr) alias_gen name=LEGACY_ALIAS_GEN(type,subtype,ptr);
#define define_alias_ref_symbolic(name,sommet,type,subtype,ptr) alias_ref_symbolic name={-1,(unary_function_eval *)sommet,LEGACY_ALIAS_GEN(type,subtype,ptr)};
#define define_alias_ref_fraction(name,numtype,numsubtype,numptr,dentype,densubtype,denptr) alias_ref_fraction name={-1,LEGACY_ALIAS_GEN(numtype,numsubtype,numptr),LEGACY_ALIAS_GEN(dentype,densubtype,denptr)};
#define define_alias_ref_complex(name,retype,resubtype,reptr,imtype,imsubtype,imptr) alias_ref_complex name={-1,0,LEGACY_ALIAS_GEN(retype,resubtype,reptr),LEGACY_ALIAS_GEN(imtype,imsubtype,imptr)};
#define define_tab2_alias_gen(name,retype,resubtype,reptr,imtype,imsubtype,imptr) alias_gen name[]={LEGACY_ALIAS_GEN(retype,resubtype,reptr),LEGACY_ALIAS_GEN(imtype,imsubtype,imptr)};
''')
    change('gen.h', '''  struct alias_ref_symbolic {
    ref_count_t ref_count;
    unary_function_eval * sommet;
#ifdef DOUBLEVAL
    longlong value;
#else
    long value ; 
#endif
    unsigned short reserved; // not used 
    signed char subtype;
    unsigned char type;  // see dispatch.h
  };''', '''  struct alias_ref_symbolic {
    ref_count_t ref_count;
    unary_function_eval *sommet;
    alias_gen feuille;
  };
  static_assert(sizeof(alias_ref_symbolic)==sizeof(ref_symbolic),
                "ROM symbolic layout mismatch");''')
    change('gen.h', '''  struct alias_ref_vecteur { ref_count_t ref_count; void * ptr; const alias_gen * begin; unsigned size; unsigned capacity; };
#define define_alias_ref_vecteur(name,b) alias_ref_vecteur name={-1,0,(const alias_gen *)b,sizeof(gen),sizeof(gen)};
  //#define define_alias_ref_vecteur2(name,b) alias_ref_vecteur name={-1,&b[0],&b[2],&b[2],0};
#define define_alias_ref_vecteur2(name,b) alias_ref_vecteur name={-1,0,&b[0],2*sizeof(gen),2*sizeof(gen)};''',
           '''  struct alias_ref_vecteur {
    ref_count_t ref_count;
    const alias_gen *begin,*end,*capacity;
  };
  static_assert(sizeof(alias_ref_vecteur)==sizeof(ref_vecteur),
                "ROM vector layout mismatch");
#define define_alias_ref_vecteur(name,b) alias_ref_vecteur name={-1,(const alias_gen *)b,(const alias_gen *)b+1,(const alias_gen *)b+1};
#define define_alias_ref_vecteur2(name,b) alias_ref_vecteur name={-1,&b[0],b+2,b+2};''')


def patch_standard_library(change, source):
    change('first.h', 'using stdostream=std::ostream;',
           '''using stdostream=std::ostream;
#ifndef M_PI
#define M_PI 3.14159265358979323846
#endif''')
    change('first.h',
           '#if __BYTE_ORDER__ ==__ORDER_LITTLE_ENDIAN__ && SIZEOF_VOID_P==8 //',
           '#if !defined(DOUBLEVAL) && __BYTE_ORDER__ ==__ORDER_LITTLE_ENDIAN__ && SIZEOF_VOID_P==8 //')
    change('kglobal.cc', '  void logptr(stdostream * b,GIAC_CONTEXT){',
           '''  void logptr(stdostream * b,GIAC_CONTEXT){
    if (!b){
      static stdostream sink(nullptr);
      b=&sink;
    }''')
    change('kgen.cc', '''#ifndef NSPIRE
  ostream & operator << (ostream & os,const gen & a) { return os << a.print(context0); }
#endif
''', '')
    change('console.h', '  LINE_MAX = 32,', '  CONSOLE_LINE_MAX = 32,')
    for filename in ('console.h', 'main.h', 'textGUI.h', 'kmisc.cc'):
        contents = (source / filename).read_bytes().decode('latin1')
        change(filename, contents, contents.replace('ustl::', 'std::'))
    change('kmisc.cc', 'args.type==_STRNG?(*args._STRNGptr):"input ?",s,false',
           'args.type==_STRNG?args._STRNGptr->c_str():"input ?",s,false')
    change('kmisc.cc', 'giac::syms().capacity()', 'giac::syms().size()')
    change('kmisc.cc', 'contextptr->tabptr->capacity()', 'contextptr->tabptr->size()')
    change('kmisc.cc', 'return *sptr; // ":=";', 'return sptr->c_str();')
    change('kmisc.cc', '(g.val & 0xffff0000);', '(g.val & ~0xffff);')
    change('kprog.cc', '    unsigned int i=0;\n    if ( g.type==_STRNG',
           '    int i=0;\n    if ( g.type==_STRNG')
    change('index.cc', 'sprint_int(c,i); // my_sprintf(c,"%d",i);',
           'snprintf(c,sizeof(c),"%d",i);')
    change('ksymbolic.cc', '    if (i<0){\n      if (l && s[l-1]',
           '    const unsigned magnitude=i<0?0u-unsigned(i):unsigned(i);\n'
           '    if (i<0){\n      if (l && s[l-1]')
    change('ksymbolic.cc', '''      i=-i;
    }
    switch (integer_format(contextptr)){
    case 16:
      my_sprintf(ch,"0x%X",i);
    case 8:
      my_sprintf(ch,"0o%o",i);
    default:
      sprint_int(ch,i);//my_sprintf(ch,"%d",i);
    }''', '''    }
    switch (integer_format(contextptr)){
    case 16:
      snprintf(ch,sizeof(ch),"0x%X",magnitude);
      break;
    case 8:
      snprintf(ch,sizeof(ch),"0o%o",magnitude);
      break;
    default:
      snprintf(ch,sizeof(ch),"%u",magnitude);
    }''')
    contents = (source / 'kgen.cc').read_bytes().decode('latin1')
    old = re.search(r'^#if 0 // def KMALLOC.*?^#endif\n', contents, re.M | re.S)[0]
    change('kgen.cc', old, '')
    fences = re.findall(r'^[ \t]*if \([^;]*?stack_mask[^;]*?ctrl_c=interrupted=true;\n',
                        contents, re.M)
    if len(fences) != 12:
        raise ValueError(f'Expected 12 historical allocation address checks, got {len(fences)}')
    updated = contents.replace(old, '')
    for fence in fences:
        updated = updated.replace(fence, '', 1)
    change('kgen.cc', contents.replace(old, ''), updated)

    contents = (source / 'kgen.cc').read_bytes().decode('latin1')
    start = contents.index('  void sprintfdouble(')
    end = contents.index('\n  }', start) + len('\n  }')
    change('kgen.cc', contents[start:end], '''  void sprintfdouble(char *ch,size_t capacity,const char *format,double d){
    snprintf(ch,capacity,format,d);
  }''')
    contents = (source / 'gen.h').read_bytes().decode('latin1')
    declaration = re.search(r'void sprintfdouble\([^;]+;', contents)[0]
    change('gen.h', declaration,
           'void sprintfdouble(char *ch,size_t capacity,const char *format,double d);')
    for filename in ('kgen.cc', 'kplot.cc', 'kmisc.cc'):
        contents = (source / filename).read_bytes().decode('latin1')
        change(filename, contents, re.sub(r'sprintfdouble\((s|ss),',
                                           r'sprintfdouble(\1,sizeof(\1),', contents))

    for filename, count in (('ksolve.cc', 5), ('kti89.cc', 1)):
        contents = (source / filename).read_bytes().decode('latin1')
        if contents.count('vptr_reverse(') != count:
            raise ValueError(f'{filename}: historical reverse call count changed')
        change(filename, contents, contents.replace('vptr_reverse(', 'std::reverse('))
    change('kti89.cc', '    int key;\n    GetKey(&key);',
           '    unsigned key;\n    GetKey(&key);')
    change('kti89.cc', '    return key;\n', '    return int(key);\n')
    change('kprog.cc', '  static define_unary_function_eval2_index (86,__return,&symb_return,',
           '''  static gen eval_return(const gen &arg,GIAC_CONTEXT){
    return symb_return(arg);
  }
  static define_unary_function_eval2_index (86,__return,&eval_return,''')
    contents = (source / 'kprog.cc').read_bytes().decode('latin1')
    start = contents.index('  gen * qs_comp_f=0;')
    end = contents.index('  gen _sort(', start)
    change('kprog.cc', contents[start:end], '')
    change('kprog.cc', '''    qs_comp_f = &f;
    qs_contextptr=contextptr;
    qsort(v.begin(),v.size(),sizeof(gen),qs_comp);
    // sort(v.begin(),v.end(),gen_sort(f,contextptr));''',
           '    std::stable_sort(v.begin(),v.end(),gen_sort(f,contextptr));')


def disable_python(change, source):
    change('global.h', '    int _python_compat_;\n', '')
    change('global.h', '''  int & python_compat(GIAC_CONTEXT);
  void python_compat(int b,GIAC_CONTEXT);''',
           '''  constexpr int python_compat(const context *) { return 0; }
  inline void python_compat(int,const context *) {}''')
    change('global.h', '  extern bool python_color; // global variable for syntax highlighting\n', '')
    change('global.h', '  std::string python2xcas(const std::string & s_orig,GIAC_CONTEXT);\n', '')
    remove_between(change, source, 'kglobal.cc', '  bool python_color=false;', '  static bool _complex_mode_')
    remove_between(change, source, 'kglobal.cc', '  static string remove_comment(', '  // optional, call it just before exiting')
    change('kglobal.cc', '  /* PYTHON */\n\n', '')
    contents = (source / 'kglobal.cc').read_bytes().decode('latin1')
    updates = contents.replace('!contextptr->globalptr->_python_compat_ && ', '')
    updates = updates.replace('!_python_compat_ && ', '').replace('_python_compat_(false),', '')
    updates = re.sub(r'^.*->_python_compat_=_python_compat_;\n', '', updates, flags=re.M)
    updates = re.sub(r'^.*_python_compat_=g\._python_compat_;\n', '', updates, flags=re.M)
    change('kglobal.cc', contents, updates)

    remove_between(change, source, 'kgen.cc',
                   '      if (s.size()>10 && (s.substr(0,5)=="\\"def "',
                   '      if (s.empty()){')
    remove_between(change, source, 'kprog.cc', '  // py==0 Xcas, py==1 Python-like, py==2 JS-like',
                   '  static string printasvirgule(')
    remove_between(change, source, 'kprog.cc', '  gen _python_compat(', '  gen giac_eval_level(')
    remove_between(change, source, 'kusual.cc', '    static bool alert_array_start=true;',
                   '    if (storcl_38){')
    contents = (source / 'kmisc.cc').read_bytes().decode('latin1')
    old = re.search(r'^  gen _python_list\(.*?^  define_unary_function_ptr5\( at_python_list[^\n]+\n',
                    contents, re.M | re.S)[0]
    change('kmisc.cc', old, '')
    for name in ('input_lexer.cc', 'input_lexer.ll'):
        change(name, 'if (python_compat(yyextra)){ *yylval=at_python_list; return T_UNARY_OP; } ', '')
    for name, a, b, result in (('input_parser.cc', '(yyvsp[-2])', '(yyvsp[-1])', '(yyval)'),
                                ('input_parser.yy', '$1', '$2', '$$')):
        change(name, f'''\tif ({a}==_LIST__VECT && python_compat(giac_yyget_extra(scanner))){{
           {result}=symbolic(at_python_list,{b});
        }}
        else {{''', '        {')


def disable_external_commands(change, source):
    remove_between(change, source, 'kmisc.cc', '  gen _addr(', '  static vecteur listplot(')
    remove_between(change, source, 'kprog.cc', '  bool is_address(', '  gen symb_findhelp(')
    remove_between(change, source, 'kmaple.cc', '  // open a file, returns a FILE *',
                   '  gen _blockmatrix(')
    contents = (source / 'kmisc.cc').read_bytes().decode('latin1')
    start = contents.index('  gen _giacinput(')
    end = contents.index('  static const char _input_s', start)
    change('kmisc.cc', contents[start:end], '''  gen _giacinput(const gen &args,GIAC_CONTEXT){
    if (args.type==_STRNG && args.subtype==-1)
      return args;
    return gensizeerr("Interactive input is unavailable in this UI");
  }
''')
    remove_between(change, source, 'kmaple.cc', '  void set_time(', '  gen _time(')
    contents = (source / 'kmaple.cc').read_bytes().decode('latin1')
    start = contents.index('      if (a._VECTptr->size()==2', contents.index('  gen _time('))
    end = contents.index('      return RTC_GetTicks();', start)
    change('kmaple.cc', contents[start:end], '''      if (a._VECTptr->size()==2 && a._VECTptr->front().type==_INT_ && a._VECTptr->back().type==_INT_)
        return gensizeerr("Changing the system clock is unavailable");
''')
    change('kmaple.cc', '''      unsigned t2= RTC_GetTicks();
      if (t2>=t1+32)
\treturn double(t2-t1)/double(i)/128;''', '''      const unsigned ticks_per_day=24*60*60*128;
      const unsigned elapsed=(unsigned(RTC_GetTicks())+ticks_per_day-t1)%ticks_per_day;
      if (elapsed>=32)
        return double(elapsed)/double(i)/128;''')
    contents = (source / 'kgen.cc').read_bytes().decode('latin1')
    start = contents.index('#ifdef NSPIRE\n  template<class T> nio::ios_base<T> & operator>>')
    end = contents.index('  string remove_extension(', start)
    change('kgen.cc', contents[start:end], '')


def patch_legacy_remainder(change, source):
    contents = (source / 'kmodpoly.cc').read_bytes().decode('latin1')
    start = contents.index('  static void rem(int * & r,')
    end = contents.index('\n  }', start) + len('\n  }')
    before = contents[start:end]
    pointer = '    quo=quoend-((rend-r)-(k-1));'
    if before.count(pointer) != 1:
        raise ValueError('Expected one optional quotient cursor in modular remainder')
    after = before.replace(pointer, '    quo=quoend?quoend-((rend-r)-(k-1)):0;')
    change('kmodpoly.cc', before, after)
    change('kusual.cc', '''      a %= b ;
      a -= (a>>31)*b;
      return a;''', '''      if (b==0)
        return a;
      if (b==-1)
        return 0;
      a %= b;
      if (a<0)
        a=b<0?a-b:a+b;
      return a;''')
    contents = (source / 'kusual.cc').read_bytes().decode('latin1')
    opening = contents.index('    if (args.type==_VECT && args._VECTptr->size()>1 && args._VECTptr->front().type==_STRNG){',
                             contents.index('  gen _irem('))
    ending = contents.index('    if (!check_2d_vecteur(args))', opening)
    change('kusual.cc', contents[opening:ending], '''    if (args.type==_VECT && args._VECTptr->size()>1 && args._VECTptr->front().type==_STRNG){
      const vecteur &v=*args._VECTptr;
      if (v.size()>4)
        return gendimerr(contextptr);
      const string &format=*v.front()._STRNGptr;
      string output;
      size_t arg=1;
      for (size_t pos=0;pos<format.size();){
        const char ch=format[pos++];
        if (ch!='%' || (pos<format.size() && format[pos]=='%')){
          if (ch=='%')
            ++pos;
          if (output.size()==255)
            return gensizeerr(contextptr);
          output+=ch;
          continue;
        }
        const size_t start=pos-1;
        while (pos<format.size() && strchr("-+ #0",format[pos]) && format[pos])
          ++pos;
        for (int part=0;part<2;++part){
          if (part==1){
            if (pos==format.size() || format[pos]!='.')
              break;
            ++pos;
          }
          unsigned number=0;
          while (pos<format.size() && format[pos]>='0' && format[pos]<='9'){
            number=number*10+unsigned(format[pos++]-'0');
            if (number>255)
              return gensizeerr(contextptr);
          }
        }
        if (pos==format.size() || arg==v.size())
          return gensizeerr(contextptr);
        const char conversion=format[pos++];
        const string specifier=format.substr(start,pos-start);
        const gen &value=v[arg++];
        char fragment[256];
        int length=-1;
        if (conversion && strchr("dic",conversion) && value.type==_INT_)
          length=snprintf(fragment,sizeof(fragment),specifier.c_str(),value.val);
        else if (conversion && strchr("uoxX",conversion) && value.type==_INT_)
          length=snprintf(fragment,sizeof(fragment),specifier.c_str(),unsigned(value.val));
        else if (conversion=='s' && value.type==_STRNG)
          length=snprintf(fragment,sizeof(fragment),specifier.c_str(),value._STRNGptr->c_str());
        else if (conversion && strchr("aAeEfFgG",conversion)){
          const gen numeric=evalf_double(value,1,contextptr);
          if (numeric.type==_DOUBLE_)
            length=snprintf(fragment,sizeof(fragment),specifier.c_str(),numeric._DOUBLE_val);
        }
        if (length<0 || size_t(length)>255-output.size())
          return gensizeerr(contextptr);
        output.append(fragment,size_t(length));
      }
      if (arg!=v.size())
        return gendimerr(contextptr);
      return string2gen(output,false);
    }
''')


def prepare(source, change):
    for macro in ('USTL', 'std ustl', 'NO_STDEXCEPT'):
        change('config.h', f'#define {macro}\n', '')
    change('config.h', '#define FXCG\n',
           '#define FXCG\n#define FX9860GIII 1\n#define DOUBLEVAL 1\n'
           '#define GIAC_NO_PYTHON 1\n#define KHICAS_GIAC_LEGACY 1\n')
    change('first.h', '#define _GIAC_FIRST_H_\n',
           '#define _GIAC_FIRST_H_\n#ifdef HAVE_CONFIG_H\n#include "config.h"\n#endif\n')
    change('first.h', '#ifdef FXCG\n#define clock() 0',
           '#include <cassert>\n#include <cstddef>\n#include <cstdint>\n#include <ostream>\n'
           '#include <string>\n#include <vector>\n'
           'namespace giac { using std::string; using std::vector; }\n'
           'using stdostream=std::ostream;\n\n#ifdef FXCG\n#define clock() 0')
    change('first.h', '#define RAND_MAX 2147483647',
           '#ifndef RAND_MAX\n#define RAND_MAX 2147483647\n#endif')
    change('first.h', 'typedef unsigned pid_t;\ndouble lgamma(double);',
           'inline Bidon operator << (Bidon,std::ostream &(*)(std::ostream &)){return Bidon();}')
    change('first.h', '''#ifdef DOUBLEVAL 
#undef STATIC_BUILTIN_LEXER_FUNCTIONS
// otherwise change the definition of charptr_gen in input_lexer.ll
#endif
''', '')
    change('first.h',
           'const size_t alias_name = (size_t)(ptr); const unary_function_ptr * const name = (const unary_function_ptr *) &alias_name;\n#endif\n#else',
           'const size_t alias_name = (size_t)(ptr); extern const unary_function_ptr * const name = (const unary_function_ptr *) &alias_name;\n#endif\n#else')
    change('first.h',
           'const ulonglong alias_name = ulonglong(ptr); const unary_function_ptr * const name = (const unary_function_ptr *) &alias_name;\n#else',
           'const ulonglong alias_name = ulonglong(ptr); extern const unary_function_ptr * const name = (const unary_function_ptr *) &alias_name;\n#else')
    change('global.h', '  extern volatile bool kbd_interrupted;',
           '  extern volatile bool ctrl_c,interrupted,kbd_interrupted;')
    change('global.h', '''    dbgprint_vector() : std::vector<T>::vector() { };
#if 0 //ndef GIAC_VECTOR
    dbgprint_vector(const typename std::vector<T>::const_iterator & b,const typename std::vector<T>::const_iterator & e) : std::vector<T>::vector(b,e) { };
#endif
    dbgprint_vector(const T * b,const T * e) : std::vector<T>::vector(b,e) { };
    dbgprint_vector(size_t i) : std::vector<T>::vector(i) { };
    dbgprint_vector(size_t i,const T & t) : std::vector<T>::vector(i,t) { };''',
           '''    using std::vector<T>::vector;
    dbgprint_vector()=default;
    dbgprint_vector(size_t size):std::vector<T>(size) {}''')
    change('misc.h', 'const ustl::string & s,bool status=true',
           'const std::string & s,bool status=true')
    change('misc.h', 'ustl::string & s,bool numeric,int ypos=35',
           'std::string & s,bool numeric,int ypos=35')
    change('kgen.cc', '#if 1\n#define ALLOCSMALL\n#endif',
           '// Allocation uses the tracked platform allocator.')
    patch_alias_layout(change, source)
    patch_standard_library(change, source)
    disable_python(change, source)
    disable_external_commands(change, source)
    patch_legacy_remainder(change, source)

    entries = write_registry(source)
    for name in ('input_lexer.cc', 'input_lexer.ll'):
        change(name, '''#if defined(RTOS_THREADX) || defined(__MINGW_H) || defined NSPIRE || defined FXCG || defined MS_SMART || defined(FREERTOS)
  int isatty (int ){ return 0; }
#endif
''', '')
    change('input_lexer.ll', '%option noyywrap', '%option noyywrap never-interactive')
    change('input_lexer.cc', 'b->yy_is_interactive = file ? (isatty( 0 ) > 0) : 0;',
           'b->yy_is_interactive = 0;')
    change('input_lexer.h', 'extern int giac_yylex(giac::YYSTYPE * yylval_param ,void * yyscanner);',
           'extern int giac_yylex(giac::gen *yylval_param,void *yyscanner);')
    change('input_lexer.h', '#define YY_EXTRA_TYPE  context const *',
           '#ifndef YY_EXTRA_TYPE\n#define YY_EXTRA_TYPE context const *\n#endif')
    change('input_lexer.h', '  charptr_gen * builtin_lexer_functions_begin();\n'
           '  charptr_gen * builtin_lexer_functions_end();',
           '  int find_legacy_builtin(const char *name,gen &value);')
    change('kglobal.cc', '#include "input_parser.h" \n',
           '#include "input_parser.h" \n#include "legacy_lexer_registry.inc"\n')
    text = (source / 'kglobal.cc').read_bytes().decode('latin1')
    start = text.index('      ustl::pair<charptr_gen *,charptr_gen *> p=')
    end = text.index('      lexer_tab_int_type tst=', start)
    change('kglobal.cc', text[start:end], '''      const int token=find_legacy_builtin(ts.c_str(),res);
      if (token){
        if (token==T_TO)
          res=plus_one;
        res.subtype=1;
        index_status(contextptr)=token==T_UNARY_OP;
        return token;
      }
''')
    start = text.index('  const charptr_gen_unary  builtin_lexer_functions[]')
    end = text.index('  gen make_symbolic', start)
    change('kglobal.cc', text[start:end], '')
    change('kprog.cc', '''    std::pair<charptr_gen *,charptr_gen *> p= equal_range(builtin_lexer_functions_begin(),builtin_lexer_functions_end(),charptr_gen(cs.c_str(),0),tri);
    if (p.first!=p.second && p.first!=builtin_lexer_functions_end()){
      c=p.first->second;''', '''    if (find_legacy_builtin(cs.c_str(),c)){''')

    for name in ('input_parser.cc', 'input_parser.yy'):
        change(name, '#define YYINITDEPTH 100\n#define YYMAXDEPTH 101',
               '#define YYINITDEPTH 64\n#define YYMAXDEPTH 64')
    return entries


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--memory-profile', action='store_true')
    parser.add_argument('--outline-gen', action='store_true',
                        help='Measure shared implementations for gen copying and cleanup')
    args = parser.parse_args()
    units = cas_units(args.source)
    args.output.mkdir()
    for file in args.source.iterdir():
        if file.name in units or file.suffix in ('.h', '.ll', '.yy') or file.name == 'Makefile':
            shutil.copy2(file, args.output / file.name)
    modified = set()

    def change(filename, before, after):
        file = args.output / filename
        contents = file.read_bytes().decode('latin1')
        count = contents.count(before)
        if count != 1:
            raise ValueError(f'{filename}: expected one edit, found {count} for {before[:100]!r}')
        file.write_bytes(contents.replace(before, after).encode('latin1'))
        modified.add(filename)

    entries = prepare(args.output, change)
    if args.memory_profile:
        from legacy_memory_profile import apply
        apply(change, args.output)
        from legacy_heap_profile import apply as protect_heaps
        protect_heaps(change, args.output)
        from legacy_symbol_profile import apply as protect_symbols
        protect_symbols(change, args.output)
    from legacy_desktop_streams import apply as remove_desktop_streams
    remove_desktop_streams(change, args.output)
    if args.outline_gen:
        for declaration in ('    gen(const gen & e);', '    ~gen();',
                            '    gen & operator = (const gen & a);'):
            change('gen.h', declaration,
                   '    __attribute__((noinline)) ' + declaration.strip())
    from legacy_gen_lifetime import apply as protect_gen_lifetime
    protect_gen_lifetime(change, args.output)
    from legacy_polynomial_lifetime import apply as transfer_polynomial_storage
    transfer_polynomial_storage(change, args.output)
    repo = Path(__file__).resolve().parents[1]
    for header in ('giac_memory.h', 'giac_memory_tommath.h'):
        shutil.copy2(repo / 'src' / header, args.output / header)
    (args.output / 'legacy-prepare.json').write_text(json.dumps({
        'source': str(args.source.resolve()), 'units': units, 'commands': entries,
        'modified': sorted(modified), 'memory_profile': args.memory_profile,
        'outline_gen': args.outline_gen,
        'desktop_streams_removed': True,
        'allocation_free_gen_ownership': True,
        'polynomial_storage_moves': True,
        'heap_transactions': args.memory_profile,
        'symbol_transactions': args.memory_profile,
        'files': {file.name: hashlib.sha256(file.read_bytes()).hexdigest()
                  for file in sorted(args.output.iterdir()) if file.is_file()},
        'profiles': {name: hashlib.sha256((repo / 'tools' / name).read_bytes()).hexdigest()
                     for name in ('prepare_legacy_giac.py', 'legacy_memory_profile.py',
                                  'legacy_owner_profile.py', 'giac_scanner_profile.py',
                                  'giac_memory_profile.py', 'legacy_desktop_streams.py',
                                  'legacy_gen_lifetime.py', 'legacy_heap_profile.py',
                                  'legacy_symbol_profile.py',
                                  'legacy_polynomial_lifetime.py')
                     if (repo / 'tools' / name).is_file()},
    }, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(f'{len(units)} CAS units, {len(entries)} typed registrations')


if __name__ == '__main__':
    main()
