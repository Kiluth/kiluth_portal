"""Checks for kiluth_portal/utils/customer_rules.py. No Frappe needed:

	python3 kiluth_portal/tests/test_customer_rules.py
"""

import importlib.util
import os
import sys

here = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(here, "..", "utils", "customer_rules.py")
spec = importlib.util.spec_from_file_location("customer_rules", path)
r = importlib.util.module_from_spec(spec)
spec.loader.exec_module(r)

fails = []


def check(name, cond):
	if not cond:
		fails.append(name)


have = ["Baanploypoom", "JULY WELLNESS CO., LTD.", "บริษัท แมรี่แมนูแฟ็คเจอริ่ง จำกัด", "CMCC", "Rak Chiang Mai Guesthouse", "Idol Farm"]
check("the real case", r.similar_customer("Baanploypoom Kindergarten", have) == "Baanploypoom")
check("case and spaces", r.similar_customer("baan ploypoom", have) == "Baanploypoom")
check("legal words", r.similar_customer("July Wellness Company Limited", have) == "JULY WELLNESS CO., LTD.")
check("Thai legal words", r.similar_customer("แมรี่แมนูแฟ็คเจอริ่ง", have) == "บริษัท แมรี่แมนูแฟ็คเจอริ่ง จำกัด")
check("shorter new name", r.similar_customer("Chiang Mai Guesthouse", have) == "Rak Chiang Mai Guesthouse")
check("short names exact only", r.similar_customer("CMC", have) is None)
check("short exact", r.similar_customer("cmcc", have) == "CMCC")
check("different client", r.similar_customer("Bonsoir", have) is None)
check("only legal words", r.similar_customer("Co., Ltd.", have) is None)
check("farm is not Idol Farm", r.similar_customer("Farm", have) is None)

if fails:
	print("FAIL:", *fails, sep="\n  ")
	sys.exit(1)
print("all checks passed")
