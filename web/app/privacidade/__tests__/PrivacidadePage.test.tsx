import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import PrivacidadePage from "../page";

describe("PrivacidadePage", () => {
  it("renderiza o título e as seções essenciais", () => {
    render(<PrivacidadePage />);
    expect(screen.getByRole("heading", { level: 1, name: /política de privacidade/i })).toBeInTheDocument();
    // Seções que a política precisa cobrir para valer alguma coisa.
    expect(screen.getByRole("heading", { name: /dados que coletamos/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /whoop e garmin/i })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: /seus direitos/i })).toBeInTheDocument();
  });

  it("informa o email de contato", () => {
    render(<PrivacidadePage />);
    expect(screen.getByRole("link", { name: /leandro\.sp@gmail\.com/i })).toBeInTheDocument();
  });
});
