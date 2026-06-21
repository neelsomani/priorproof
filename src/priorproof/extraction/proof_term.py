from __future__ import annotations

import shlex
import shutil
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import date
from pathlib import Path


@dataclass(frozen=True)
class ProofTermExtractorConfig:
    repo: Path
    out: Path
    commit: str
    proof_date: date
    imports: tuple[str, ...] = ("Mathlib",)
    module_prefixes: tuple[str, ...] = ("Mathlib",)
    include_private: bool = False
    lean_command: tuple[str, ...] | None = None


def extract_proof_terms(config: ProofTermExtractorConfig) -> None:
    config.out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="priorproof-lean-") as tmp:
        script = Path(tmp) / "PriorProofExtract.lean"
        script.write_text(LEAN_EXTRACTOR, encoding="utf-8")
        command = extractor_command(config, script)
        completed = subprocess.run(
            command,
            cwd=str(config.repo),
            check=False,
            text=True,
            capture_output=True,
        )
        if completed.returncode != 0:
            display = " ".join(shlex.quote(part) for part in command)
            raise RuntimeError(
                f"Proof-term extractor failed ({completed.returncode}): {display}\n"
                f"stdout:\n{completed.stdout}\n"
                f"stderr:\n{completed.stderr}"
            )


def extractor_command(config: ProofTermExtractorConfig, script: Path) -> tuple[str, ...]:
    if config.lean_command:
        base = config.lean_command
    elif shutil.which("lake"):
        base = ("lake", "env", "lean")
    elif shutil.which("lean"):
        base = ("lean",)
    else:
        raise RuntimeError(
            "Cannot run proof-term extraction because neither `lake` nor `lean` is on PATH. "
            "Install Lean/elan and run this command from a Mathlib checkout."
        )
    args = [
        *base,
        "--run",
        str(script),
        "--out",
        str(config.out),
        "--commit",
        config.commit,
        "--proof-date",
        config.proof_date.isoformat(),
    ]
    for module in config.imports:
        args.extend(["--import", module])
    for prefix in config.module_prefixes:
        args.extend(["--module-prefix", prefix])
    if config.include_private:
        args.append("--include-private")
    return tuple(args)


LEAN_EXTRACTOR = r'''
import Lean

set_option maxHeartbeats 0

open Lean

structure ExtractConfig where
  out : System.FilePath := "priorproof-extract.jsonl"
  commit : String := ""
  proofDate : String := ""
  imports : Array Name := #[]
  modulePrefixes : Array String := #[]
  includePrivate : Bool := false

def parseName (s : String) : Name :=
  s.splitOn "." |>.foldl (init := Name.anonymous) fun acc part => acc.str part

partial def parseArgs : List String → ExtractConfig → Except String ExtractConfig
  | [], cfg => Except.ok cfg
  | "--out" :: value :: rest, cfg => parseArgs rest { cfg with out := value }
  | "--commit" :: value :: rest, cfg => parseArgs rest { cfg with commit := value }
  | "--proof-date" :: value :: rest, cfg => parseArgs rest { cfg with proofDate := value }
  | "--import" :: value :: rest, cfg => parseArgs rest { cfg with imports := cfg.imports.push (parseName value) }
  | "--module-prefix" :: value :: rest, cfg =>
      parseArgs rest { cfg with modulePrefixes := cfg.modulePrefixes.push value }
  | "--include-private" :: rest, cfg => parseArgs rest { cfg with includePrivate := true }
  | flag :: _, _ => Except.error s!"unknown or incomplete argument: {flag}"

def moduleNameOf? (env : Environment) (name : Name) : Option Name := do
  let idx ← env.getModuleIdxFor? name
  env.header.moduleNames[idx]?

def namespaceOf (name : Name) : String :=
  match name with
  | .anonymous => ""
  | .str p _ => if p.isAnonymous then "" else p.toString
  | .num p _ => if p.isAnonymous then "" else p.toString

def isPriorProofInternalName (name : Name) : Bool :=
  let text := name.toString
  text.startsWith "_private" || text.contains "._private" || text.contains ".match_" ||
    text.contains "._proof_" || text.contains ".proof_" || text.contains "._" ||
    text.contains ".eq_"

def moduleAllowed (cfg : ExtractConfig) (moduleName : Name) : Bool :=
  if cfg.modulePrefixes.isEmpty then
    true
  else
    cfg.modulePrefixes.any fun pfx => moduleName.toString.startsWith pfx

def constKind (info : ConstantInfo) : String :=
  match info with
  | .axiomInfo _ => "axiom"
  | .defnInfo _ => "def"
  | .thmInfo _ => "theorem"
  | .opaqueInfo _ => "opaque"
  | .quotInfo _ => "quot"
  | .inductInfo _ => "inductive"
  | .ctorInfo _ => "constructor"
  | .recInfo _ => "recursor"

def moduleForDependency (env : Environment) (name : Name) : String :=
  match moduleNameOf? env name with
  | some moduleName => moduleName.toString
  | none => ""

def dependencyJson (env : Environment) (name : Name) : Json :=
  let info? := env.find? name
  let kind := match info? with
    | some info => constKind info
    | none => "const"
  Json.mkObj [
    ("name", Json.str name.toString),
    ("kind", Json.str kind),
    ("module", Json.str (moduleForDependency env name)),
    ("namespace", Json.str (namespaceOf name)),
    ("source", Json.str "proof_term")
  ]

def exprConstants (e : Expr) : Array Name :=
  e.getUsedConstants.qsort fun left right => left.toString < right.toString

def thmDependencies (self : Name) (value : Expr) : Array Name := Id.run do
  let mut seen : NameSet := {}
  let mut output : Array Name := #[]
  for name in exprConstants value do
    unless name == self || seen.contains name do
      seen := seen.insert name
      output := output.push name
  return output

def theoremRow (cfg : ExtractConfig) (env : Environment) (name : Name) (type value : Expr) : MetaM Json := do
  let moduleName := match moduleNameOf? env name with
    | some moduleName => moduleName.toString
    | none => ""
  let dependencies := thmDependencies name value
  let statement := (← PrettyPrinter.ppExpr type).pretty
  return Json.mkObj [
    ("name", Json.str name.toString),
    ("statement", Json.str statement),
    ("proof_date", Json.str cfg.proofDate),
    ("module", Json.str moduleName),
    ("namespace", Json.str (namespaceOf name)),
    ("commit", Json.str cfg.commit),
    ("dependencies", Json.arr (dependencies.map (dependencyJson env))),
    ("dependency_edges", Json.arr #[]),
    ("subterms", Json.arr #[]),
    ("metadata", Json.mkObj [
      ("source_adapter", Json.str "priorproof_proof_term"),
      ("extractor", Json.str "lean_environment_getUsedConstants")
    ])
  ]

def collectTheorems (cfg : ExtractConfig) (env : Environment) : MetaM (Array Json) := do
  let mut rows : Array Json := #[]
  for i in [:env.header.moduleNames.size] do
    let moduleName := env.header.moduleNames[i]!
    if moduleAllowed cfg moduleName then
      let moduleData := env.header.moduleData[i]!
      for j in [:moduleData.constNames.size] do
        let name := moduleData.constNames[j]!
        if !cfg.includePrivate && isPriorProofInternalName name then
          continue
        let info := moduleData.constants[j]!
        match info with
        | .thmInfo val =>
            rows := rows.push (← theoremRow cfg env name val.type val.value)
        | _ => pure ()
  return rows.qsort fun left right => Lean.Json.compress left < Lean.Json.compress right

def writeJsonl (path : System.FilePath) (rows : Array Json) : IO Unit := do
  let handle ← IO.FS.Handle.mk path IO.FS.Mode.write
  for row in rows do
    handle.putStrLn (Json.compress row)

unsafe def main (args : List String) : IO UInt32 := do
  let cfg ← match parseArgs args {} with
    | Except.ok cfg => pure cfg
    | Except.error msg =>
        IO.eprintln msg
        return 2
  let opts := Options.empty.set `maxHeartbeats (0 : Nat)
  let imports := cfg.imports.map fun module => ({ module := module } : Import)
  let env ← importModules imports opts 0
  let rows ← (Meta.MetaM.run' (collectTheorems cfg env)).toIO'
    { fileName := "<priorproof-extractor>", fileMap := default, options := opts, maxHeartbeats := 0 }
    { env := env }
  writeJsonl cfg.out rows
  return 0
'''
