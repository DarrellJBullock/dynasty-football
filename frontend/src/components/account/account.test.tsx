import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { api, ApiError } from "@/lib/api";
import { hardNavigate } from "@/lib/navigation";
import { AccountMenu } from "@/components/shell/AccountMenu";
import { AccountView } from "./AccountView";
import { AuthForm, safeNext } from "./AuthForm";
import { ForgotPasswordForm, ResetPasswordForm } from "./PasswordReset";

const search = { value: "" };
vi.mock("next/navigation", () => ({ useSearchParams: () => new URLSearchParams(search.value) }));
vi.mock("@/lib/navigation", () => ({ hardNavigate: vi.fn() }));
vi.mock("@/lib/api", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/lib/api")>();
  return { ...actual, api: { signIn: vi.fn(), signUp: vi.fn(), signOut: vi.fn(), me: vi.fn(),
    changePassword: vi.fn(), deleteAccount: vi.fn(), forgotPassword: vi.fn(),
    resetPassword: vi.fn() } };
});
const mocked = vi.mocked(api);
const user = { id: 1, email: "coach@example.test", has_league: true };

beforeEach(() => {
  vi.clearAllMocks();
  search.value = "";
});

async function fillIn(email: string, password: string) {
  await userEvent.type(screen.getByLabelText("Email"), email);
  await userEvent.type(screen.getByLabelText("Password"), password);
}

describe("AuthForm", () => {
  it("signs in and goes back where the visitor was headed", async () => {
    search.value = "next=/roster";
    mocked.signIn.mockResolvedValue(user);
    render(<AuthForm mode="signin" />);
    await fillIn("coach@example.test", "secret-pass");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(mocked.signIn).toHaveBeenCalledWith({ email: "coach@example.test", password: "secret-pass" });
    expect(hardNavigate).toHaveBeenCalledWith("/roster");
  });

  it("shows why signing in failed", async () => {
    mocked.signIn.mockRejectedValue(new ApiError(401, "Wrong email or password."));
    render(<AuthForm mode="signin" />);
    await fillIn("coach@example.test", "nope-nope");
    await userEvent.click(screen.getByRole("button", { name: "Sign in" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Wrong email or password.");
    expect(hardNavigate).not.toHaveBeenCalled();
    expect(screen.getByRole("link", { name: "Create an account" })).toHaveAttribute("href", "/signup");
  });

  it("creates an account and goes to build its first league", async () => {
    mocked.signUp.mockResolvedValue({ ...user, has_league: false });
    render(<AuthForm mode="signup" />);
    expect(screen.getByRole("form", { name: "Create an account" })).toBeInTheDocument();
    await fillIn("new@example.test", "long enough");
    await userEvent.click(screen.getByRole("button", { name: "Create account" }));
    expect(mocked.signUp).toHaveBeenCalledWith({ email: "new@example.test", password: "long enough" });
    expect(hardNavigate).toHaveBeenCalledWith("/leagues/new");
  });

  it("only follows ?next= within the site", () => {
    expect(safeNext("/games/4/watch?play=2")).toBe("/games/4/watch?play=2");
    expect(safeNext("//evil.example")).toBe("/");
    expect(safeNext("https://evil.example")).toBe("/");
    expect(safeNext(null)).toBe("/");
  });
});

describe("AccountView", () => {
  it("changes the password", async () => {
    mocked.changePassword.mockResolvedValue(undefined);
    render(<AccountView user={user} />);
    const form = screen.getByRole("form", { name: "Change password" });
    await userEvent.type(within(form).getByLabelText("Current password"), "old-password");
    await userEvent.type(within(form).getByLabelText("New password"), "new-password");
    await userEvent.type(within(form).getByLabelText("New password again"), "new-passw0rd");
    await userEvent.click(within(form).getByRole("button", { name: "Change password" }));
    expect(within(form).getByRole("alert")).toHaveTextContent("don't match");
    expect(mocked.changePassword).not.toHaveBeenCalled();

    await userEvent.clear(within(form).getByLabelText("New password again"));
    await userEvent.type(within(form).getByLabelText("New password again"), "new-password");
    await userEvent.click(within(form).getByRole("button", { name: "Change password" }));
    expect(mocked.changePassword).toHaveBeenCalledWith("old-password", "new-password");
    expect(await within(form).findByRole("status")).toHaveTextContent("Password changed.");
  });

  it("deletes the account after the password is entered", async () => {
    mocked.deleteAccount.mockRejectedValueOnce(new ApiError(403, "Your password is wrong."))
      .mockResolvedValueOnce(undefined);
    render(<AccountView user={user} />);
    expect(screen.getByText("coach@example.test")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Delete account…" }));
    const dialog = screen.getByRole("dialog", { name: "Delete your account?" });
    const confirm = within(dialog).getByRole("button", { name: "Delete everything" });
    expect(confirm).toBeDisabled();
    await userEvent.type(within(dialog).getByLabelText("Password"), "wrong-one");
    await userEvent.click(confirm);
    expect(await within(dialog).findByRole("alert")).toHaveTextContent("Your password is wrong.");
    await userEvent.click(confirm);
    await waitFor(() => expect(hardNavigate).toHaveBeenCalledWith("/signup"));
  });
});

describe("AccountMenu", () => {
  it("shows who's signed in and signs out", async () => {
    mocked.me.mockResolvedValue(user);
    mocked.signOut.mockResolvedValue(undefined);
    render(<AccountMenu />);
    const menu = screen.getByRole("group", { name: "Account" });
    expect(await within(menu).findByRole("link", { name: "coach@example.test" }))
      .toHaveAttribute("href", "/account");
    await userEvent.click(within(menu).getByRole("button", { name: "Sign out" }));
    expect(mocked.signOut).toHaveBeenCalled();
    expect(hardNavigate).toHaveBeenCalledWith("/signin");
  });
});

describe("Password reset", () => {
  it("is linked from signing in", () => {
    render(<AuthForm mode="signin" />);
    expect(screen.getByRole("link", { name: "Forgot your password?" }))
      .toHaveAttribute("href", "/forgot-password");
  });

  it("emails a link", async () => {
    mocked.forgotPassword.mockResolvedValue({ detail: "If there's an account for that email, a reset link is on its way." });
    render(<ForgotPasswordForm />);
    await userEvent.type(screen.getByLabelText("Email"), "coach@example.test");
    await userEvent.click(screen.getByRole("button", { name: "Email me a link" }));
    expect(mocked.forgotPassword).toHaveBeenCalledWith("coach@example.test");
    expect(await screen.findByRole("status")).toHaveTextContent("a reset link is on its way");
  });

  it("sets a new password with the link's token", async () => {
    search.value = "token=abc123";
    mocked.resetPassword.mockRejectedValueOnce(new ApiError(400, "This reset link has expired or was already used."))
      .mockResolvedValueOnce(undefined);
    render(<ResetPasswordForm />);
    await userEvent.type(screen.getByLabelText("New password"), "new-password");
    await userEvent.type(screen.getByLabelText("New password again"), "different");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(screen.getByRole("alert")).toHaveTextContent("don't match");

    await userEvent.clear(screen.getByLabelText("New password again"));
    await userEvent.type(screen.getByLabelText("New password again"), "new-password");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("expired");
    await userEvent.click(screen.getByRole("button", { name: "Set new password" }));
    expect(mocked.resetPassword).toHaveBeenLastCalledWith("abc123", "new-password");
    expect(await screen.findByRole("status")).toHaveTextContent("Your password is changed");
    expect(screen.getByRole("link", { name: "Sign in" })).toHaveAttribute("href", "/signin");
  });

  it("needs the link's token", () => {
    render(<ResetPasswordForm />);
    expect(screen.getByRole("button", { name: "Set new password" })).toBeDisabled();
    expect(screen.getByRole("link", { name: "Ask for one" })).toHaveAttribute("href", "/forgot-password");
  });
});
