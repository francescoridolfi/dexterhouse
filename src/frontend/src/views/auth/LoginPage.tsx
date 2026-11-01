// SPDX-License-Identifier: AGPL-3.0-or-later
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { type FormEvent, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";

import { ApiError } from "../../api/client.ts";
import { api } from "../../api/endpoints.ts";
import { keys } from "../../api/queries.ts";
import { Button } from "../../components/Button.tsx";
import { TextField } from "../../components/Fields.tsx";

/** Session login: the server sets an HttpOnly cookie; the SPA never sees a token. */
export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const client = useQueryClient();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");

  useEffect(() => {
    void api.csrf().catch(() => undefined);
  }, []);

  const login = useMutation({
    mutationFn: async () => {
      await api.csrf();
      return api.login(username, password);
    },
    onSuccess: (user) => {
      client.setQueryData(keys.me, user);
      const from = (location.state as { from?: string } | null)?.from;
      void navigate(from && from !== "/login" ? from : "/projects", { replace: true });
    },
  });

  const submit = (event: FormEvent) => {
    event.preventDefault();
    login.mutate();
  };

  const error =
    login.error instanceof ApiError && login.error.status === 401
      ? t("login.invalid")
      : login.error
        ? t("error.unknown")
        : undefined;

  return (
    <main className="grid min-h-screen place-items-center bg-bg p-4 text-fg">
      <form
        onSubmit={submit}
        className="w-full max-w-sm space-y-4 rounded-card border border-line bg-surface p-6 shadow-card"
      >
        <div className="flex items-center gap-2">
          <img src="/favicon.svg" alt="" className="size-8" />
          <h1 className="text-xl font-semibold">DexterHouse</h1>
        </div>
        <p className="text-sm text-muted">{t("login.subtitle")}</p>
        <TextField
          label={t("login.username")}
          autoComplete="username"
          value={username}
          onChange={(e) => setUsername(e.target.value)}
          required
        />
        <TextField
          label={t("login.password")}
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          required
        />
        {error ? (
          <p role="alert" className="text-sm text-failed">
            {error}
          </p>
        ) : null}
        <Button type="submit" variant="primary" busy={login.isPending} className="w-full">
          {t("login.submit")}
        </Button>
      </form>
    </main>
  );
}
