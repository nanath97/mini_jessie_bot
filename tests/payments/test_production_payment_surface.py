"""SEC-002 source guards; never import the live bot or contact payment services."""
import ast
from pathlib import Path
import re
import unittest


ROOT = Path(__file__).resolve().parents[2]


class ProductionPaymentSurfaceTests(unittest.TestCase):
    def test_python_does_not_register_removed_debit_endpoint(self):
        tree = ast.parse((ROOT / 'main.py').read_text(encoding='utf-8-sig'))
        strings = [node.value for node in ast.walk(tree)
                   if isinstance(node, ast.Constant) and isinstance(node.value, str)]
        self.assertFalse(any('/test-off-session' in value for value in strings))
        self.assertFalse(any(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
                             and node.name == 'test_off_session' for node in ast.walk(tree)))

    def test_bridge_does_not_expose_or_forward_removed_debit_endpoint(self):
        source = (ROOT / 'Bridge/server.js').read_text(encoding='utf-8-sig')
        self.assertNotIn('/test-off-session', source)
        self.assertNotRegex(source, r'PaymentIntent\s*\.\s*create\s*\('
                            r'|paymentIntents\s*\.\s*create\s*\('
                            r'|api\.stripe\.com/[^\s\"\x27]*payment_intents')
        self.assertFalse(re.search(r'\bcustomer_id\b', source)
                         and re.search(r'\bpayment_method_id\b', source))

    def test_only_quote_collection_handler_creates_confirmed_intents(self):
        # Scan the operational Python modules, including HTTP entrypoints.
        # Existing encaisser tests exercise its authorization and debt checks.
        creators = []
        for path in sorted(ROOT.glob('*.py')):
            tree = ast.parse(path.read_text(encoding='utf-8-sig'))

            class FindCreators(ast.NodeVisitor):
                owner = None

                def visit_FunctionDef(self, node):
                    previous = self.owner
                    self.owner = node.name
                    self.generic_visit(node)
                    self.owner = previous

                visit_AsyncFunctionDef = visit_FunctionDef

                def visit_Call(self, node):
                    name = ast.unparse(node.func)
                    if name.endswith(('PaymentIntent.create', 'payment_intents.create')):
                        creators.append((path.name, self.owner))
                    self.generic_visit(node)

            FindCreators().visit(tree)
        self.assertEqual(creators, [('bott_webhook.py', 'encaisser_off_session')])


if __name__ == '__main__':
    unittest.main()
