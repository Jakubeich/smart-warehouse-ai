import { Input } from "../src/components/ui/input";
import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import { Button, ErrorPanel, EmptyState } from "../src/components/shared";
describe("accessible interactions", () => {
  it("disabled actions cannot submit", () => {
    const action = vi.fn();
    render(
      <Button disabled onClick={action}>
        Start
      </Button>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Start" }));
    expect(action).not.toHaveBeenCalled();
  });
  it("surfaces actionable backend errors", () => {
    render(<ErrorPanel error={new Error("No robot can reach task pickup")} />);
    expect(screen.getByRole("alert")).toHaveTextContent(
      "Žádný robot se nedostane ke stanici nakládky",
    );
  });
  it("explains empty data without fabricated metrics", () => {
    render(
      <EmptyState
        title="No experiments"
        description="Run an experiment to collect data."
      />,
    );
    expect(screen.getByText("No experiments")).toBeVisible();
  });
});

it("Czech input validation clears after the value is corrected", () => {
  render(<Input aria-label="Počet" type="number" min={1} required />);
  const input = screen.getByRole("spinbutton", {
    name: "Počet",
  }) as HTMLInputElement;
  fireEvent.invalid(input);
  expect(input.validationMessage).toBe("Vyplňte toto pole.");
  fireEvent.input(input, { target: { value: "2" } });
  expect(input.checkValidity()).toBe(true);
});
