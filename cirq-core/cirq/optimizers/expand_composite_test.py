# Copyright 2018 The Cirq Developers
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Tests for the expand composite optimization pass."""
import cirq


def assert_equal_mod_empty(expected, actual):
    actual = cirq.drop_empty_moments(actual)
    assert expected == actual, f'EXPECTED {expected} : ACTUAL {actual}'


def assert_optimizes(no_decomp, expected, actual):
    with cirq.testing.assert_deprecated("Use cirq.expand_composite", deadline='v1.0'):
        expander = cirq.ExpandComposite(no_decomp) if no_decomp else cirq.ExpandComposite()
        expander(expected)
        if actual:
            assert_equal_mod_empty(expected, actual)


def test_empty_circuit():
    circuit = cirq.Circuit()
    assert_optimizes(None, circuit.copy(), circuit)


def test_empty_moment():
    circuit = cirq.Circuit([])
    assert_optimizes(None, circuit.copy(), circuit)


def test_ignore_non_composite():
    q0, q1 = cirq.LineQubit.range(2)
    circuit = cirq.Circuit()
    circuit.append([cirq.X(q0), cirq.Y(q1), cirq.CZ(q0, q1), cirq.Z(q0)])
    assert_optimizes(None, circuit.copy(), circuit)


def test_composite_default():
    q0, q1 = cirq.LineQubit.range(2)
    cnot = cirq.CNOT(q0, q1)
    circuit = cirq.Circuit()
    circuit.append(cnot)
    expected = cirq.Circuit()
    expected.append([cirq.Y(q1) ** -0.5, cirq.CZ(q0, q1), cirq.Y(q1) ** 0.5])
    assert_optimizes(None, circuit, expected)


def test_multiple_composite_default():
    q0, q1 = cirq.LineQubit.range(2)
    cnot = cirq.CNOT(q0, q1)
    circuit = cirq.Circuit()
    circuit.append([cnot, cnot])
    expected = cirq.Circuit()
    decomp = [cirq.Y(q1) ** -0.5, cirq.CZ(q0, q1), cirq.Y(q1) ** 0.5]
    expected.append([decomp, decomp])
    assert_optimizes(None, circuit, expected)
    assert_equal_mod_empty(expected, circuit)


def test_mix_composite_non_composite():
    q0, q1 = cirq.LineQubit.range(2)

    actual = cirq.Circuit(cirq.X(q0), cirq.CNOT(q0, q1), cirq.X(q1))

    expected = cirq.Circuit(
        cirq.X(q0),
        cirq.Y(q1) ** -0.5,
        cirq.CZ(q0, q1),
        cirq.Y(q1) ** 0.5,
        cirq.X(q1),
        strategy=cirq.InsertStrategy.NEW,
    )
    assert_optimizes(None, actual, expected)


def test_recursive_composite():
    q0, q1 = cirq.LineQubit.range(2)
    swap = cirq.SWAP(q0, q1)
    circuit = cirq.Circuit()
    circuit.append(swap)

    expected = cirq.Circuit(
        cirq.Y(q1) ** -0.5,
        cirq.CZ(q0, q1),
        cirq.Y(q1) ** 0.5,
        cirq.Y(q0) ** -0.5,
        cirq.CZ(q1, q0),
        cirq.Y(q0) ** 0.5,
        cirq.Y(q1) ** -0.5,
        cirq.CZ(q0, q1),
        cirq.Y(q1) ** 0.5,
    )
    assert_optimizes(None, circuit, expected)


def test_decompose_returns_not_flat_op_tree():
    class DummyGate(cirq.SingleQubitGate):
        def _decompose_(self, qubits):
            (q0,) = qubits
            # Yield a tuple of gates instead of yielding a gate
            yield cirq.X(q0),

    q0 = cirq.NamedQubit('q0')
    circuit = cirq.Circuit(DummyGate()(q0))

    expected = cirq.Circuit(cirq.X(q0))
    assert_optimizes(None, circuit, expected)


def test_decompose_returns_deep_op_tree():
    class DummyGate(cirq.testing.TwoQubitGate):
        def _decompose_(self, qubits):
            q0, q1 = qubits
            # Yield a tuple
            yield ((cirq.X(q0), cirq.Y(q0)), cirq.Z(q0))
            # Yield nested lists
            yield [cirq.X(q0), [cirq.Y(q0), cirq.Z(q0)]]

            def generator(depth):
                if depth <= 0:
                    yield cirq.CZ(q0, q1), cirq.Y(q0)
                else:
                    yield cirq.X(q0), generator(depth - 1)
                    yield cirq.Z(q0)

            # Yield nested generators
            yield generator(2)

    q0, q1 = cirq.LineQubit.range(2)
    circuit = cirq.Circuit(DummyGate()(q0, q1))

    expected = cirq.Circuit(
        cirq.X(q0),
        cirq.Y(q0),
        cirq.Z(q0),  # From tuple
        cirq.X(q0),
        cirq.Y(q0),
        cirq.Z(q0),  # From nested lists
        # From nested generators
        cirq.X(q0),
        cirq.X(q0),
        cirq.CZ(q0, q1),
        cirq.Y(q0),
        cirq.Z(q0),
        cirq.Z(q0),
    )
    assert_optimizes(None, circuit, expected)


def test_non_recursive_expansion():
    qubits = [cirq.NamedQubit(s) for s in 'xy']
    no_decomp = lambda op: (isinstance(op, cirq.GateOperation) and op.gate == cirq.ISWAP)
    unexpanded_circuit = cirq.Circuit(cirq.ISWAP(*qubits))

    circuit = unexpanded_circuit.__copy__()
    assert_optimizes(no_decomp, circuit, unexpanded_circuit)

    no_decomp = lambda op: (
        isinstance(op, cirq.GateOperation)
        and isinstance(op.gate, (cirq.CNotPowGate, cirq.HPowGate))
    )
    circuit = unexpanded_circuit.__copy__()
    assert_optimizes(no_decomp, circuit, None)
    actual_text_diagram = circuit.to_text_diagram().strip()
    expected_text_diagram = """
x: ───@───H───X───S───X───S^-1───H───@───
      │       │       │              │
y: ───X───────@───────@──────────────X───
    """.strip()
    assert actual_text_diagram == expected_text_diagram
