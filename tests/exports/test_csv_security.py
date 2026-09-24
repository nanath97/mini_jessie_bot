"""SEC-022: exercise the real CSV helper and export handler without live services."""
import ast
import csv
from datetime import datetime
from decimal import Decimal
from io import StringIO
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch


ROOT = Path(__file__).resolve().parents[2]
tree = ast.parse((ROOT / 'bott_webhook.py').read_text(encoding='utf-8-sig'))
functions = [node for node in tree.body
             if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
             and node.name in ('neutralize_csv_cell', 'export_factures')]
assert len(functions) == 2
for function in functions:
    function.decorator_list = []
namespace = {'types': SimpleNamespace(CallbackQuery=object)}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(ROOT / 'bott_webhook.py'), 'exec'), namespace)
neutralize_csv_cell = namespace['neutralize_csv_cell']
DANGEROUS = ('=SUM(A1:A2)', '+123', '-1+1', '@SUM(A1:A2)',
             '\tvalue', '\rvalue', '\nvalue')


class CsvCellTests(unittest.TestCase):
    def test_dangerous_prefixes_are_quoted_without_losing_content(self):
        for value in DANGEROUS:
            with self.subTest(value=value):
                self.assertEqual(neutralize_csv_cell(value), "'" + value)

    def test_normal_strings_unchanged(self):
        for value in ('', 'Facture 2026-001', 'client@example.com', 'a;b"c', "'safe"):
            with self.subTest(value=value):
                self.assertEqual(neutralize_csv_cell(value), value)

    def test_numbers_keep_their_type_and_value(self):
        for value in (0, 123, -123, 12.34, -12.34, Decimal('12.34')):
            with self.subTest(value=value):
                self.assertIs(neutralize_csv_cell(value), value)


class CsvExportTests(unittest.IsolatedAsyncioTestCase):
    async def test_every_external_text_column_is_protected_and_amounts_stay_numeric(self):
        fields = ('Invoice Number', 'Paid At', 'Client Key', 'Buyer Name',
                  'Buyer Email', 'Buyer Phone', 'Buyer Address Line 1',
                  'Buyer Address Line 2', 'Buyer Postal Code', 'Buyer City',
                  'Buyer Country', 'Buyer Type', 'Buyer Company Name',
                  'Buyer SIRET', 'Buyer VAT', 'Caption')
        records = []
        clients = {}
        # Also exercise the Date fallback and the enterprise-name client branch.
        for index, value in enumerate(DANGEROUS):
            data = dict.fromkeys(fields, value)
            data['Amount Cents'] = 12345
            if index == 0:
                data['Paid At'] = ''
                data['Date'] = value
            records.append({'fields': data})
            clients[value] = dict.fromkeys(('type_client', 'entreprise_nom', 'siret', 'tva'), value)
            if index == 0:
                clients[value]['type_client'] = 'entreprise'

        bot = SimpleNamespace(send_document=AsyncMock(), send_message=AsyncMock())
        callback = SimpleNamespace(from_user=SimpleNamespace(id=123), answer=AsyncMock())
        request = Mock()
        request.get.return_value.json.return_value = {'records': records}
        rows = []
        real_writer = csv.writer

        def capture_writer(*args, **kwargs):
            writer = real_writer(*args, **kwargs)

            def writerow(row):
                rows.append(list(row))
                return writer.writerow(row)

            return SimpleNamespace(writerow=writerow)

        with patch.dict(namespace, {
            'bot': bot, 'requests': request, 'BASE_ID': 'offline',
            'AIRTABLE_API_KEY': 'offline', 'datetime': datetime,
            'get_pwa_client_by_email': lambda email: clients[email],
            'types': SimpleNamespace(InputFile=lambda stream, filename: stream),
        }), patch('csv.writer', side_effect=capture_writer):
            await namespace['export_factures'](callback)

        bot.send_message.assert_not_awaited()
        bot.send_document.assert_awaited_once()
        self.assertEqual(len(rows), 1 + len(DANGEROUS))
        for index, (value, row) in enumerate(zip(DANGEROUS, rows[1:])):
            with self.subTest(value=value):
                self.assertEqual(len(row), 27)
                for column in [*range(20), 25]:
                    expected = 'entreprise' if index == 0 and column == 2 else "'" + value
                    self.assertEqual(row[column], expected, f'column {column}')
                self.assertEqual(row[20:24], [123.45, 0, 0.0, 123.45])
                self.assertTrue(all(isinstance(cell, (int, float)) for cell in row[20:24]))
                self.assertEqual((row[24], row[26]), ('EUR', 'PRESTATION'))
        document = bot.send_document.call_args.kwargs['document']
        decoded = list(csv.reader(StringIO(document.getvalue().decode('utf-8-sig')), delimiter=';'))
        self.assertEqual(decoded, [[str(cell) for cell in row] for row in rows])


if __name__ == '__main__':
    unittest.main()
