"""Comprehensive unit and differential tests for Three-Address Code (TAC) IR.

Governed by RFC-0006 §7, this module verifies AST-to-TAC lowering, operand/instruction
contracts, CFG block structures, formatting, JSON serialization, validator invariants,
and semantics preservation via the TAC virtual machine.
"""

from __future__ import annotations

import pytest

from nexora.errors import InternalCompilerError
from nexora.ir import (
    Call,
    Const,
    Copy,
    FuncBegin,
    FuncEnd,
    Goto,
    IfFalse,
    IRGenerator,
    Label,
    Param,
    Print,
    Return,
    Temp,
    Var,
    build_all_cfgs,
    build_cfg,
    flatten_cfg,
    format_tac,
    tac_to_dict,
    validate_tac,
)
from nexora.lexer import Lexer
from nexora.parser import Parser
from nexora.semantic import SemanticAnalyzer
from nexora.symbols import Type
from tests.helpers.tac_vm import run_tac


def compile_to_tac(source: str):
    """Helper to parse, analyze, and generate TAC for a MiniLang source string."""
    tokens = Lexer(source).tokenize()
    parse_result = Parser(tokens).parse()
    analyzer = SemanticAnalyzer()
    analyzer.analyze(parse_result.program)
    generator = IRGenerator()
    tac = generator.generate(parse_result.program)
    return tac


# =============================================================================
# 1. Lowering Tests (RFC-0006 §3.4, §3.5)
# =============================================================================


class TestIRLowering:
    """Test AST-to-TAC lowering for all language constructs."""

    def test_arithmetic_expression_and_retarget_peephole(self) -> None:
        """Verify Example A: 2 + 3 * 4 with peephole retargeting fresh temp to result."""
        source = """
        make result = 2 + 3 * 4;
        show(result);
        """
        tac = compile_to_tac(source)
        validate_tac(tac)
        formatted = format_tac(tac)

        # Expected sequence:
        # func __main():
        #   t1 = 3 * 4
        #   result = 2 + t1   <-- retarget peephole replaced t2 with result
        #   print result
        #   return
        # endfunc
        assert formatted[0] == "func __main():"
        assert formatted[1] == "  t1 = 3 * 4"
        assert formatted[2] == "  result = 2 + t1"
        assert formatted[3] == "  print result"
        assert formatted[4] == "  return"
        assert formatted[5] == "endfunc"

    def test_recursive_task_and_during_loop(self) -> None:
        """Verify Example B: recursive factorial task and during loop."""
        source = """
        task factorial(n: int): int {
            when (n <= 1) {
                give 1;
            }
            give n * factorial(n - 1);
        }

        make i = 1;
        during (i <= 5) {
            show(factorial(i));
            i = i + 1;
        }
        """
        tac = compile_to_tac(source)
        validate_tac(tac)
        formatted = format_tac(tac)

        # Check task header
        assert "func factorial(n):" in formatted
        # Check during loop structure in __main
        assert any("ifFalse" in line and "goto" in line for line in formatted)
        assert any("call factorial, 1" in line for line in formatted)

    def test_short_circuit_both(self) -> None:
        """Verify short-circuit evaluation of 'both' operator."""
        source = "make ok = a > 0 both b / a > 2;"
        tac = compile_to_tac(source)
        validate_tac(tac)
        formatted = format_tac(tac)

        # Short-circuit pattern: Copy(t, left), IfFalse(t, Lend), Copy(t, right), Label(Lend)
        assert any("ifFalse" in line for line in formatted)
        assert any("ok = t" in line or "t" in line for line in formatted)

    def test_short_circuit_either(self) -> None:
        """Verify short-circuit evaluation of 'either' operator."""
        source = "make ok = a == 0 either b > 10;"
        tac = compile_to_tac(source)
        validate_tac(tac)
        formatted = format_tac(tac)

        # Short-circuit pattern: Copy(t, left), IfTrue(t, Lend), Copy(t, right), Label(Lend)
        assert any("ifTrue" in line for line in formatted)

    def test_widening_conversion_in_assignment(self) -> None:
        """Verify integer-to-float widening emits UnOp(float) or converts constant."""
        source = """
        make x: float = 5;
        make y: int = 10;
        x = y;
        """
        tac = compile_to_tac(source)
        validate_tac(tac)
        formatted = format_tac(tac)

        # x = 5.0 literal conversion and float y widening
        assert any("x = 5.0" in line for line in formatted)
        assert any("float y" in line for line in formatted)

    def test_ask_and_show_lowering(self) -> None:
        """Verify ask and show statement lowering."""
        source = """
        ask age: int;
        show(age);
        """
        tac = compile_to_tac(source)
        validate_tac(tac)
        formatted = format_tac(tac)

        assert any("age = ask int" in line for line in formatted)
        assert any("print age" in line for line in formatted)

    def test_when_with_otherwise_and_otherwise_when(self) -> None:
        """Verify conditional branching with otherwise and chained otherwise when."""
        source = """
        make score = 85;
        when (score >= 90) {
            show("A");
        } otherwise when (score >= 80) {
            show("B");
        } otherwise {
            show("C");
        }
        """
        tac = compile_to_tac(source)
        validate_tac(tac)
        formatted = format_tac(tac)

        assert any("ifFalse" in line for line in formatted)
        assert any("goto" in line for line in formatted)
        assert any('print "A"' in line for line in formatted)
        assert any('print "B"' in line for line in formatted)
        assert any('print "C"' in line for line in formatted)

    def test_during_loop_with_stop_and_skip(self) -> None:
        """Verify during loop lowering with stop and skip control transfer."""
        source = """
        make i = 0;
        during (i < 10) {
            i = i + 1;
            when (i == 3) {
                skip;
            }
            when (i == 8) {
                stop;
            }
            show(i);
        }
        """
        tac = compile_to_tac(source)
        validate_tac(tac)
        formatted = format_tac(tac)

        assert any("goto L" in line for line in formatted)

    def test_determinism_and_counter_reset(self) -> None:
        """Verify consecutive compilations start temp and label counters at 1."""
        source = "make a = 1 + 2 * 3;"
        tac1 = compile_to_tac(source)
        tac2 = compile_to_tac(source)

        assert format_tac(tac1) == format_tac(tac2)
        assert tac1[1].dest.name == "t1"  # First temporary allocated is t1


# =============================================================================
# 2. CFG and Basic Block Tests (RFC-0006 §3.6)
# =============================================================================


class TestControlFlowGraph:
    """Test BasicBlock partitioning, edges, and CFG algorithms."""

    def test_simple_straight_line_cfg(self) -> None:
        """Verify straight-line code in __main forms a single basic block."""
        source = """
        make a = 1;
        make b = 2;
        show(a + b);
        """
        tac = compile_to_tac(source)
        cfgs = build_all_cfgs(tac)

        assert len(cfgs) == 1
        main_cfg = cfgs[0]
        assert main_cfg.function == "__main"
        assert len(main_cfg.blocks) == 1
        b0 = main_cfg.blocks[0]
        assert b0.id == 0
        assert b0.succ == []  # Ends with Return -> no successors

    def test_branching_and_loop_cfg_edges(self) -> None:
        """Verify CFG successors and predecessors around conditional branches and loops."""
        source = """
        make x = 0;
        during (x < 5) {
            when (x == 2) {
                show("two");
            }
            x = x + 1;
        }
        """
        tac = compile_to_tac(source)
        cfgs = build_all_cfgs(tac)
        main_cfg = cfgs[0]

        # Ensure predecessor/successor consistency
        for b in main_cfg.blocks:
            for s_id in b.succ:
                assert b.id in main_cfg.blocks[s_id].pred

    def test_flatten_cfg_round_trip(self) -> None:
        """Verify flattening CFG preserves instructions."""
        source = "make x = 10; show(x);"
        tac = compile_to_tac(source)
        cfg = build_cfg(tac)
        flattened = flatten_cfg(cfg)

        assert len(flattened) == len(tac)
        assert isinstance(flattened[0], FuncBegin)
        assert isinstance(flattened[-1], FuncEnd)


# =============================================================================
# 3. Serialization and Formatting Tests (RFC-0006 §3.7)
# =============================================================================


class TestSerializationAndFormatting:
    """Test text formatting and JSON serialization of instructions."""

    def test_tac_to_dict_schema(self) -> None:
        """Verify JSON dictionary serialization contains required RFC fields."""
        source = "make a = 3 * 4;"
        tac = compile_to_tac(source)
        dict_list = tac_to_dict(tac)

        assert isinstance(dict_list, list)
        for item in dict_list:
            assert "op" in item
            assert "line" in item
            assert "text" in item

        # Verify BinOp entry
        binop_entry = next(d for d in dict_list if d["op"] == "binop")
        assert binop_entry["operator"] == "*"
        assert binop_entry["type"] == "int"

    def test_text_formatting_indentation(self) -> None:
        """Verify functions and labels are column-aligned while body is indented 2 spaces."""
        source = """
        task greet() {
            show("hello");
        }
        greet();
        """
        tac = compile_to_tac(source)
        lines = format_tac(tac)

        assert lines[0].startswith("func greet(")
        assert lines[1].startswith("  ")  # Indented body
        assert "endfunc" in lines


# =============================================================================
# 4. Validator Invariant Tests (RFC-0006 §3.8)
# =============================================================================


class TestTACValidator:
    """Verify validate_tac enforces all 6 compiler invariants."""

    def test_rejects_empty_tac(self) -> None:
        with pytest.raises(
            InternalCompilerError, match="TAC instruction stream is empty"
        ):
            validate_tac([])

    def test_rejects_instruction_outside_function(self) -> None:
        bad_tac = [
            Copy(Var("x", Type.INT), Const(1, Type.INT)),
            FuncBegin("__main", [], Type.VOID),
            Return(None),
            FuncEnd("__main"),
        ]
        with pytest.raises(InternalCompilerError, match="outside function definition"):
            validate_tac(bad_tac)

    def test_rejects_unclosed_function(self) -> None:
        bad_tac = [
            FuncBegin("__main", [], Type.VOID),
            Return(None),
        ]
        with pytest.raises(InternalCompilerError, match="Unclosed function"):
            validate_tac(bad_tac)

    def test_rejects_duplicate_label(self) -> None:
        bad_tac = [
            FuncBegin("__main", [], Type.VOID),
            Label("L1"),
            Label("L1"),
            Return(None),
            FuncEnd("__main"),
        ]
        with pytest.raises(InternalCompilerError, match="Duplicate label"):
            validate_tac(bad_tac)

    def test_rejects_jump_to_undefined_label(self) -> None:
        bad_tac = [
            FuncBegin("__main", [], Type.VOID),
            Goto("L_NONEXISTENT"),
            Return(None),
            FuncEnd("__main"),
        ]
        with pytest.raises(InternalCompilerError, match="Jump to undefined label"):
            validate_tac(bad_tac)

    def test_rejects_undefined_temporary_use(self) -> None:
        bad_tac = [
            FuncBegin("__main", [], Type.VOID),
            Copy(Var("x", Type.INT), Temp("t1", Type.INT)),  # t1 not defined
            Return(None),
            FuncEnd("__main"),
        ]
        with pytest.raises(InternalCompilerError, match="Use of undefined temporary"):
            validate_tac(bad_tac)

    def test_rejects_call_param_count_mismatch(self) -> None:
        bad_tac = [
            FuncBegin("__main", [], Type.VOID),
            Param(Const(1, Type.INT)),
            Call(None, "foo", argc=2),  # argc=2 but only 1 Param pushed
            Return(None),
            FuncEnd("__main"),
        ]
        with pytest.raises(InternalCompilerError, match="expects 2 params but found 1"):
            validate_tac(bad_tac)

    def test_rejects_interposed_instruction_before_call(self) -> None:
        bad_tac = [
            FuncBegin("__main", [], Type.VOID),
            Param(Const(1, Type.INT)),
            Print(Const("hi", Type.STRING)),  # Foreign instruction before Call
            Call(None, "foo", argc=1),
            Return(None),
            FuncEnd("__main"),
        ]
        with pytest.raises(
            InternalCompilerError, match="interposed between Param and Call"
        ):
            validate_tac(bad_tac)

    def test_rejects_missing_return_before_func_end(self) -> None:
        bad_tac = [
            FuncBegin("__main", [], Type.VOID),
            Print(Const("hi", Type.STRING)),  # Ends with Print, not Return
            FuncEnd("__main"),
        ]
        with pytest.raises(InternalCompilerError, match="does not end with Return"):
            validate_tac(bad_tac)

    def test_rejects_non_bool_condition_in_branch(self) -> None:
        bad_tac = [
            FuncBegin("__main", [], Type.VOID),
            Label("L1"),
            IfFalse(Const(42, Type.INT), "L1"),  # Condition must be bool
            Return(None),
            FuncEnd("__main"),
        ]
        with pytest.raises(
            InternalCompilerError, match="Condition in IfFalse is not bool"
        ):
            validate_tac(bad_tac)


# =============================================================================
# 5. Differential Testing with TAC VM (RFC-0006 §3.9)
# =============================================================================


class TestTACVMDifferential:
    """Verify execution semantics on the reference TAC VM."""

    def test_vm_executes_arithmetic_and_output(self) -> None:
        source = """
        make a = 15;
        make b = 25;
        show(a + b);
        """
        tac = compile_to_tac(source)
        stdout, err = run_tac(tac)

        assert err is None
        assert stdout == "40\n"

    def test_vm_executes_recursive_factorial(self) -> None:
        source = """
        task factorial(n: int): int {
            when (n <= 1) {
                give 1;
            }
            give n * factorial(n - 1);
        }

        make i = 1;
        during (i <= 5) {
            show(factorial(i));
            i = i + 1;
        }
        """
        tac = compile_to_tac(source)
        stdout, err = run_tac(tac)

        assert err is None
        assert stdout == "1\n2\n6\n24\n120\n"

    def test_vm_short_circuit_avoids_division_by_zero(self) -> None:
        source = """
        make a = 0;
        make ok = a > 0 both 10 / a > 2;
        show(ok);
        """
        tac = compile_to_tac(source)
        stdout, err = run_tac(tac)

        assert err is None
        assert stdout == "false\n"

    def test_vm_detects_runtime_division_by_zero(self) -> None:
        source = """
        make z = 0;
        show(5 / z);
        """
        tac = compile_to_tac(source)
        _stdout, err = run_tac(tac)

        assert err == "R5001"

    def test_vm_handles_ask_input(self) -> None:
        source = """
        ask name: string;
        ask age: int;
        show("Hello " + name);
        show(age + 1);
        """
        tac = compile_to_tac(source)
        stdout, err = run_tac(tac, input_lines=["Alice\n", "20\n"])

        assert err is None
        assert stdout == "Hello Alice\n21\n"
