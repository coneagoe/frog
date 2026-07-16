import { importPositions } from "./api-client";

it("posts import positions payloads", async () => {
  const fetchMock = vi.fn().mockResolvedValue(new Response(JSON.stringify({ imported_count: 1, lots_count: 1 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);

  await importPositions(7, {
    positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
  });

  expect(fetchMock).toHaveBeenCalledWith(
    "/api/paper/accounts/7/positions/import",
    expect.objectContaining({
      method: "POST",
      body: JSON.stringify({
        positions: [{ symbol: "000001", quantity: 100, cost_price: "10.23", buy_trade_date: "2026-01-15" }]
      })
    })
  );
});
