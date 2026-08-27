from __future__ import annotations

import unittest
from pathlib import Path

from reconciliation_as_code.runtime import run_reconciliation_runtime
from reconciliation_as_code.spec import load_spec


ROOT = Path(__file__).resolve().parents[1]
SAP = ROOT / "examples" / "sap-s4hana"


def run_pack(relative: str) -> dict:
    spec_path = SAP / relative
    spec = load_spec(spec_path)
    return run_reconciliation_runtime(
        spec,
        base_dir=spec_path.parent,
        spec_path=spec_path,
        backend="python",
    )


def check(result: dict, check_id: str) -> dict:
    return next(item for item in result["checks"] if item["id"] == check_id)


class SapStarterPackTests(unittest.TestCase):
    def test_customer_to_bp_changed_id_hierarchy_finds_expected_failures(self) -> None:
        result = run_pack("customer-to-bp/reconciliation.yaml")

        self.assertEqual("failed", result["status"])
        self.assertEqual(2, result["summary"]["identity_components"])
        self.assertEqual(2, result["summary"]["child_collections"])
        self.assertEqual("passed", check(result, "name")["status"])
        self.assertEqual("passed", check(result, "grouping")["status"])
        self.assertEqual("failed", check(result, "child:addresses:postal-code")["status"])
        sales_coverage = check(result, "child:sales_areas:coverage")
        self.assertEqual("failed", sales_coverage["status"])
        self.assertEqual(1, sales_coverage["metrics"]["missing_in_target"])
        self.assertIn("identity_crosswalk", result["inputs"])

    def test_supplier_to_bp_changed_id_bank_detail_finds_expected_failure(self) -> None:
        result = run_pack("supplier-to-bp/reconciliation.yaml")

        self.assertEqual("failed", result["status"])
        self.assertEqual(2, result["summary"]["identity_components"])
        self.assertEqual("passed", check(result, "payment-terms")["status"])
        iban = check(result, "child:bank_accounts:iban")
        self.assertEqual("failed", iban["status"])
        self.assertEqual(1, iban["metrics"]["mismatches"])

    def test_material_pack_normalizes_ids_maps_type_and_localizes_plant_failure(self) -> None:
        result = run_pack("material-product/reconciliation.yaml")

        self.assertEqual("failed", result["status"])
        self.assertEqual(2, result["summary"]["matched_records"])
        self.assertEqual("passed", check(result, "material-type")["status"])
        self.assertEqual("passed", check(result, "child:plant_views:coverage")["status"])
        min_lot = check(result, "child:plant_views:min-lot")
        self.assertEqual("failed", min_lot["status"])
        self.assertEqual(1, min_lot["metrics"]["mismatches"])

    def test_finance_pack_finds_account_and_grouped_balance_variance(self) -> None:
        result = run_pack("finance-inventory-balances/finance-reconciliation.yaml")

        self.assertEqual("failed", result["status"])
        self.assertEqual(3, result["summary"]["matched_records"])
        account = check(result, "amount-by-account")
        grouped = check(result, "amount-by-company-currency")
        grand = check(result, "grand-total")
        self.assertEqual(1, account["metrics"]["mismatches"])
        self.assertEqual(1, grouped["metrics"]["groups_failed"])
        self.assertEqual("failed", grand["status"])

    def test_inventory_pack_finds_record_and_plant_quantity_variance(self) -> None:
        result = run_pack("finance-inventory-balances/inventory-reconciliation.yaml")

        self.assertEqual("failed", result["status"])
        self.assertEqual(3, result["summary"]["matched_records"])
        quantity = check(result, "quantity-by-material-plant")
        grouped = check(result, "quantity-by-plant")
        self.assertEqual(1, quantity["metrics"]["mismatches"])
        self.assertEqual(1, grouped["metrics"]["groups_failed"])
        self.assertEqual("failed", check(result, "grand-quantity")["status"])


if __name__ == "__main__":
    unittest.main()
