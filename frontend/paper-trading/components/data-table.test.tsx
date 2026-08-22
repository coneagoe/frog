import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { DataTable, compareSortValues } from "./data-table";

type Row = {
  id: string;
  name: string;
  qty: number;
  note: string | null;
};

const rows: Row[] = [
  { id: "b", name: "Beta", qty: 2, note: "z" },
  { id: "a", name: "Alpha", qty: 10, note: null },
  { id: "c", name: "Gamma", qty: 1, note: "m" }
];

function renderTable() {
  render(
    <DataTable
      columns={[
        { key: "name", header: "Name", render: (row) => row.name, sortValue: (row) => row.name },
        { key: "qty", header: "Qty", align: "right", render: (row) => row.qty, sortValue: (row) => row.qty },
        { key: "note", header: "Note", render: (row) => row.note ?? "-", sortValue: (row) => row.note },
        { key: "fixed", header: "Fixed", render: (row) => row.id }
      ]}
      emptyTitle="No rows"
      getRowKey={(row) => row.id}
      rows={rows}
    />
  );
}

function cellTexts(columnIndex: number): string[] {
  return screen.getAllByRole("row").slice(1).map((row) => within(row).getAllByRole("cell")[columnIndex].textContent ?? "");
}

describe("compareSortValues", () => {
  it("keeps missing values last in both directions", () => {
    expect(compareSortValues(null, 1, "asc")).toBe(1);
    expect(compareSortValues(1, null, "asc")).toBe(-1);
    expect(compareSortValues(null, 1, "desc")).toBe(1);
    expect(compareSortValues("a", "", "desc")).toBe(-1);
  });
});

describe("DataTable sorting", () => {
  it("leaves headers without sortValue as static text", () => {
    renderTable();
    const fixedHeader = screen.getByRole("columnheader", { name: "Fixed" });
    expect(within(fixedHeader).queryByRole("button")).not.toBeInTheDocument();
    expect(fixedHeader).not.toHaveAttribute("aria-sort");
  });

  it("cycles a text column through ascending, descending, and original order", async () => {
    const user = userEvent.setup();
    renderTable();

    const nameHeader = screen.getByRole("columnheader", { name: "Name" });
    expect(nameHeader).toHaveAttribute("aria-sort", "none");
    expect(cellTexts(0)).toEqual(["Beta", "Alpha", "Gamma"]);

    await user.click(within(nameHeader).getByRole("button", { name: "Name" }));
    expect(nameHeader).toHaveAttribute("aria-sort", "ascending");
    expect(cellTexts(0)).toEqual(["Alpha", "Beta", "Gamma"]);

    await user.click(within(nameHeader).getByRole("button", { name: "Name" }));
    expect(nameHeader).toHaveAttribute("aria-sort", "descending");
    expect(cellTexts(0)).toEqual(["Gamma", "Beta", "Alpha"]);

    await user.click(within(nameHeader).getByRole("button", { name: "Name" }));
    expect(nameHeader).toHaveAttribute("aria-sort", "none");
    expect(cellTexts(0)).toEqual(["Beta", "Alpha", "Gamma"]);
  });

  it("sorts numbers numerically and keeps nulls last", async () => {
    const user = userEvent.setup();
    renderTable();

    await user.click(within(screen.getByRole("columnheader", { name: "Qty" })).getByRole("button", { name: "Qty" }));
    expect(cellTexts(1)).toEqual(["1", "2", "10"]);

    await user.click(within(screen.getByRole("columnheader", { name: "Note" })).getByRole("button", { name: "Note" }));
    expect(cellTexts(2)).toEqual(["m", "z", "-"]);
  });
});
