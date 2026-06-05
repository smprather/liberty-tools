// Boolean-expression parser (Liberty grammar). Precedence, low -> high:
//   OR (| +)  <  XOR (^)  <  AND (& * or juxtaposition)  <  NOT (! ~ prefix, ' suffix)
// Produces an AST of { op, ... } nodes:
//   {op:'var', name}  {op:'const', val:0|1}
//   {op:'not', a}     {op:'and'|'or'|'xor', args:[...]}
const OPS = "!~&*|+^'()";

export function parse(input) {
  const p = new P(input);
  const e = p.parseOr();
  p.ws();
  if (!p.eof()) throw new Error(`unexpected '${p.s[p.i]}' at position ${p.i}`);
  return e;
}

class P {
  constructor(s) { this.s = s; this.i = 0; }
  ws() { while (this.i < this.s.length && /\s/.test(this.s[this.i])) this.i++; }
  peek() { return this.s[this.i]; }
  eof() { return this.i >= this.s.length; }
  eat(ch) { if (this.peek() === ch) { this.i++; return true; } return false; }

  parseOr() {
    let e = this.parseXor();
    for (;;) { this.ws(); if (this.eat("|") || this.eat("+")) e = { op: "or", args: [e, this.parseXor()] }; else return e; }
  }
  parseXor() {
    let e = this.parseAnd();
    for (;;) { this.ws(); if (this.eat("^")) e = { op: "xor", args: [e, this.parseAnd()] }; else return e; }
  }
  parseAnd() {
    let e = this.parseNot();
    for (;;) {
      this.ws();
      if (this.eat("&") || this.eat("*")) e = { op: "and", args: [e, this.parseNot()] };
      else if (this.atPrimary()) e = { op: "and", args: [e, this.parseNot()] }; // juxtaposition = AND
      else return e;
    }
  }
  atPrimary() {
    let j = this.i;
    while (j < this.s.length && /\s/.test(this.s[j])) j++;
    const c = this.s[j];
    return c !== undefined && !"|+^&*')".includes(c);
  }
  parseNot() {
    this.ws();
    if (this.eat("!") || this.eat("~")) return { op: "not", a: this.parseNot() };
    let e = this.parsePrimary();
    for (;;) { this.ws(); if (this.eat("'")) e = { op: "not", a: e }; else return e; }
  }
  parsePrimary() {
    this.ws();
    if (this.eat("(")) {
      const e = this.parseOr();
      this.ws();
      if (!this.eat(")")) throw new Error(`expected ')' at position ${this.i}`);
      return e;
    }
    const id = this.ident();
    if (id === "1" || id === "true" || id === "TRUE") return { op: "const", val: 1 };
    if (id === "0" || id === "false" || id === "FALSE") return { op: "const", val: 0 };
    return { op: "var", name: id };
  }
  ident() {
    this.ws();
    const st = this.i;
    while (this.i < this.s.length) {
      const c = this.s[this.i];
      if (/\s/.test(c) || OPS.includes(c)) break;
      this.i++;
    }
    if (this.i === st) throw new Error(`expected identifier at position ${this.i}`);
    return this.s.slice(st, this.i);
  }
}
