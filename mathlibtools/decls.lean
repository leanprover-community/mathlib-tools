import data.list.sort meta.expr system.io

open tactic declaration environment io io.fs (put_str_ln close)

-- The next instance is there to prevent PyYAML trying to be too smart
meta def my_name_to_string : has_to_string name :=
⟨λ n, "\"" ++ to_string n ++ "\""⟩

local attribute [instance] my_name_to_string

meta def pos_line (p : option pos) : string :=
match p with
| some x := to_string x.line
| _      := ""
end

meta def file_name (p : option string) : string :=
match p with
| some x := x
| _      := ""
end

meta def print_item_crawl (env : environment) (h : handle) (decl : declaration) : io unit :=
let name := decl.to_name in
do
   put_str_ln h ((to_string name) ++ ":"), 
   put_str_ln h  ("  File: " ++ file_name (env.decl_olean name)),
   put_str_ln h ("  Line: " ++ pos_line (env.decl_pos name))

/-- itersplit l n will cut a list l into 2^n pieces (not preserving order) -/
meta def itersplit {α} : list α → ℕ → list (list α)
| l 0 := [l]
| l 1 := let (l1, l2) := l.split in [l1, l2]
| l (k+2) := let (l1, l2) := l.split in itersplit l1 (k+1) ++ itersplit l2 (k+1)

meta def main : io unit :=
do curr_env ← run_tactic get_env,
   h ← mk_file_handle "decls.yaml" mode.write,
   let decls := curr_env.fold [] list.cons,
   let filtered_decls := decls.filter
     (λ x, not (to_name x).is_internal),
   let pieces := itersplit filtered_decls 3,
   pieces.mmap' (λ l, l.mmap' (print_item_crawl curr_env h)),
   close h
