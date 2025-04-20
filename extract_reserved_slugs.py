import csv

slugs = []

with open("websites.csv") as websites:
    for place, domain, popularity in csv.reader(websites):
        for name in domain.split(".")[:-1]:
            if len(name) > 2:
                slugs.append(name)

slug_set = frozenset(slugs)
with open("src/ganglion/reserved_slugs.py", "wt") as reserved_file:
    reserved_file.write("# Generated with extract_reserved_slugs.py\n")
    reserved_file.write(f"RESERVED_SLUGS={slug_set!r}")
