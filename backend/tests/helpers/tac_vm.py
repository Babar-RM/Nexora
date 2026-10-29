"""Reference Three-Address Code (TAC) interpreter for differential testing.

Governed by RFC-0006 §3.9, this module provides an isolated TAC virtual machine
used to verify that AST lowering and TAC transformations preserve execution
semantics independently of target code generators.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from nexora.ir import (
    Ask,
    BinOp,
    Call,
    Const,
    Copy,
    FuncBegin,
    FuncEnd,
    Goto,
    IfFalse,
    IfTrue,
    Label,
    Operand,
    Param,
    Print,
    Return,
    TACInstr,
    Temp,
    UnOp,
    Var,
)
from nexora.symbols import Type


class TACVMError(Exception):
    """Raised during TAC VM execution for runtime errors with an error code."""

    def __init__(self, code: str, message: str) -> None:
        """Initialize TACVMError."""
        self.code = code
        self.message = message
        super().__init__(f"[{code}] {message}")


class TACFrame:
    """Activation frame for a function call in the TAC VM."""

    def __init__(
        self,
        func_name: str,
        caller_dest: Var | Temp | None = None,
        return_pc: int = 0,
    ) -> None:
        """Initialize frame with local variable storage and return address."""
        self.func_name: str = func_name
        self.locals: dict[str, Any] = {}
        self.caller_dest: Var | Temp | None = caller_dest
        self.return_pc: int = return_pc
        self.pc: int = 0


class TACVM:
    """Virtual Machine that interprets flat Three-Address Code."""

    def __init__(
        self,
        tac: Sequence[TACInstr],
        input_lines: Sequence[str] | None = None,
        max_steps: int = 200_000,
    ) -> None:
        """Initialize TAC VM with instructions, input queue, and safety step bound."""
        self.tac: list[TACInstr] = list(tac)
        self.input_queue: list[str] = list(input_lines or [])
        self.max_steps: int = max_steps
        self.stdout_chunks: list[str] = []

        # Function map: name -> (FuncBegin, instrs)
        self.functions: dict[str, tuple[FuncBegin, list[TACInstr]]] = {}
        # Label maps: func_name -> {label_name -> index_in_instrs}
        self.label_maps: dict[str, dict[str, int]] = {}

        self._index_functions()

    def _index_functions(self) -> None:
        """Scan instructions to map functions and label positions."""
        current_func: FuncBegin | None = None
        current_body: list[TACInstr] = []

        for instr in self.tac:
            if isinstance(instr, FuncBegin):
                current_func = instr
                current_body = []
            elif isinstance(instr, FuncEnd):
                if current_func is not None:
                    self.functions[current_func.name] = (current_func, current_body)
                    label_map: dict[str, int] = {}
                    for idx, body_instr in enumerate(current_body):
                        if isinstance(body_instr, Label):
                            label_map[body_instr.name] = idx
                    self.label_maps[current_func.name] = label_map
                current_func = None
                current_body = []
            elif current_func is not None:
                current_body.append(instr)

    def eval_operand(
        self, op: Operand, frame: TACFrame, globals_dict: dict[str, Any]
    ) -> Any:
        """Evaluate an operand to a concrete runtime value."""
        if isinstance(op, Const):
            return op.value
        if isinstance(op, (Var, Temp)):
            if op.name in frame.locals:
                return frame.locals[op.name]
            if op.name in globals_dict:
                return globals_dict[op.name]
            raise TACVMError(
                "R5006", f"Variable '{op.name}' used before initialization"
            )
        raise TACVMError("R5005", f"Unknown operand type: {type(op)}")

    def run(self) -> tuple[str, str | None]:
        """Execute TAC until completion or error, returning (stdout_text, error_code)."""
        if "__main" not in self.functions:
            return "", "R5005"

        globals_dict: dict[str, Any] = {}
        param_stack: list[Any] = []
        call_stack: list[TACFrame] = [TACFrame("__main")]
        steps = 0

        while call_stack:
            steps += 1
            if steps > self.max_steps:
                return "".join(self.stdout_chunks), "R5002"

            frame = call_stack[-1]
            _func_begin, body = self.functions[frame.func_name]

            if frame.pc >= len(body):
                # Reached end of function without explicit Return
                call_stack.pop()
                continue

            instr = body[frame.pc]
            frame.pc += 1

            try:
                if isinstance(instr, Label):
                    continue

                if isinstance(instr, Copy):
                    val = self.eval_operand(instr.src, frame, globals_dict)
                    frame.locals[instr.dest.name] = val
                    if frame.func_name == "__main":
                        globals_dict[instr.dest.name] = val

                elif isinstance(instr, BinOp):
                    l_val = self.eval_operand(instr.left, frame, globals_dict)
                    r_val = self.eval_operand(instr.right, frame, globals_dict)
                    res = self._exec_binop(instr.op, l_val, r_val)
                    frame.locals[instr.dest.name] = res
                    if frame.func_name == "__main":
                        globals_dict[instr.dest.name] = res

                elif isinstance(instr, UnOp):
                    val = self.eval_operand(instr.operand, frame, globals_dict)
                    if instr.op == "-":
                        res = -val
                    elif instr.op == "not":
                        res = not val
                    elif instr.op == "float":
                        res = float(val)
                    else:
                        raise TACVMError("R5005", f"Unknown unary operator: {instr.op}")
                    frame.locals[instr.dest.name] = res
                    if frame.func_name == "__main":
                        globals_dict[instr.dest.name] = res

                elif isinstance(instr, Goto):
                    target_pc = self.label_maps[frame.func_name].get(instr.target)
                    if target_pc is None:
                        raise TACVMError(
                            "R5005", f"Goto to unknown label: {instr.target}"
                        )
                    frame.pc = target_pc

                elif isinstance(instr, IfFalse):
                    cond_val = self.eval_operand(instr.cond, frame, globals_dict)
                    if not cond_val:
                        target_pc = self.label_maps[frame.func_name].get(instr.target)
                        if target_pc is None:
                            raise TACVMError(
                                "R5005", f"IfFalse to unknown label: {instr.target}"
                            )
                        frame.pc = target_pc

                elif isinstance(instr, IfTrue):
                    cond_val = self.eval_operand(instr.cond, frame, globals_dict)
                    if cond_val:
                        target_pc = self.label_maps[frame.func_name].get(instr.target)
                        if target_pc is None:
                            raise TACVMError(
                                "R5005", f"IfTrue to unknown label: {instr.target}"
                            )
                        frame.pc = target_pc

                elif isinstance(instr, Param):
                    arg_val = self.eval_operand(instr.arg, frame, globals_dict)
                    param_stack.append(arg_val)

                elif isinstance(instr, Call):
                    if len(call_stack) > 1000:
                        raise TACVMError("R5003", "Maximum recursion depth exceeded")

                    target_func = self.functions.get(instr.func)
                    if target_func is None:
                        raise TACVMError(
                            "R5005", f"Call to unknown function: {instr.func}"
                        )

                    target_begin, _ = target_func
                    new_frame = TACFrame(
                        func_name=instr.func,
                        caller_dest=instr.dest,
                        return_pc=frame.pc,
                    )
                    # Pop arguments in order
                    args: list[Any] = []
                    for _ in range(instr.argc):
                        if not param_stack:
                            raise TACVMError(
                                "R5005", f"Param underflow on call to {instr.func}"
                            )
                        args.append(param_stack.pop())
                    args.reverse()

                    for (param_name, _), arg_val in zip(target_begin.params, args):
                        new_frame.locals[param_name] = arg_val

                    call_stack.append(new_frame)

                elif isinstance(instr, Return):
                    ret_val = None
                    if instr.value is not None:
                        ret_val = self.eval_operand(instr.value, frame, globals_dict)

                    finished_frame = call_stack.pop()
                    if not call_stack:
                        # Exited __main
                        break

                    caller_frame = call_stack[-1]
                    if finished_frame.caller_dest is not None:
                        caller_frame.locals[finished_frame.caller_dest.name] = ret_val
                        if caller_frame.func_name == "__main":
                            globals_dict[finished_frame.caller_dest.name] = ret_val

                elif isinstance(instr, Print):
                    val = self.eval_operand(instr.value, frame, globals_dict)
                    self._output_value(val)

                elif isinstance(instr, Ask):
                    raw_input = self.input_queue.pop(0) if self.input_queue else ""
                    parsed_val: Any
                    if instr.type == Type.INT:
                        try:
                            parsed_val = int(raw_input.strip())
                        except ValueError as err:
                            raise TACVMError("R5006", "Invalid int input") from err
                    elif instr.type == Type.FLOAT:
                        try:
                            parsed_val = float(raw_input.strip())
                        except ValueError as err:
                            raise TACVMError("R5006", "Invalid float input") from err
                    else:
                        parsed_val = raw_input.rstrip("\r\n")

                    frame.locals[instr.dest.name] = parsed_val
                    if frame.func_name == "__main":
                        globals_dict[instr.dest.name] = parsed_val

            except TACVMError as err:
                return "".join(self.stdout_chunks), err.code

        return "".join(self.stdout_chunks), None

    def _exec_binop(self, op: str, left: Any, right: Any) -> Any:
        """Execute a binary operation with MiniLang / Python semantics."""
        if op == "+":
            return left + right
        if op == "-":
            return left - right
        if op == "*":
            return left * right
        if op == "/":
            if right == 0:
                raise TACVMError("R5001", "Division by zero")
            return left / right
        if op == "%":
            if right == 0:
                raise TACVMError("R5001", "Modulo by zero")
            return left % right
        if op == "==":
            return left == right
        if op == "!=":
            return left != right
        if op == "<":
            return left < right
        if op == "<=":
            return left <= right
        if op == ">":
            return left > right
        if op == ">=":
            return left >= right
        raise TACVMError("R5005", f"Unknown binary operator: {op}")

    def _output_value(self, val: Any) -> None:
        """Format and append printed output according to MiniLang specifications."""
        if isinstance(val, bool):
            text = "true" if val else "false"
        elif isinstance(val, float):
            text = repr(val)
        else:
            text = str(val)
        self.stdout_chunks.append(f"{text}\n")


def run_tac(
    tac: Sequence[TACInstr],
    input_lines: Sequence[str] | None = None,
    max_steps: int = 200_000,
) -> tuple[str, str | None]:
    """Execute TAC instructions using the reference VM and return (stdout, error_code)."""
    vm = TACVM(tac=tac, input_lines=input_lines, max_steps=max_steps)
    return vm.run()
