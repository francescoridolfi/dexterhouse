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
import { useNow } from "../../utils/useNow.ts";

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
    <main className="relative grid min-h-screen place-items-center overflow-hidden p-4 text-fg">
      <div aria-hidden className="os-wallpaper absolute inset-0" />
      <LockClock />
      <form
        onSubmit={submit}
        className="glass glass-rim os-window-in relative w-full max-w-sm space-y-4 rounded-[28px] p-7"
      >
        <div className="flex flex-col items-center gap-3 text-center">
          <span className="grid size-20 place-items-center rounded-full bg-gradient-to-b from-white/25 to-white/5 shadow-[inset_0_1px_0_rgb(255_255_255/0.4),0_10px_30px_-8px_rgb(0_0_0/0.6)]">
            <img src="/favicon.svg" alt="" className="size-11" />
          </span>
          <h1 className="text-xl font-semibold">DexterHouse</h1>
          <p className="text-sm text-muted">{t("login.subtitle")}</p>
        </div>
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
          <p role="alert" className="text-center text-sm text-failed">
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

function LockClock() {
  const { i18n } = useTranslation();
  const now = useNow(15_000);
  if (now === 0) return null;
  const date = new Date(now);
  const locale = i18n.language === "it" ? "it-IT" : "en-GB";
  return (
    <div
      aria-hidden
      className="pointer-events-none absolute top-[7vh] inset-x-0 text-center text-white/85 max-sm:hidden [@media(max-height:820px)]:hidden"
    >
      <p className="text-lg font-medium capitalize">
        {date.toLocaleDateString(locale, { weekday: "long", day: "numeric", month: "long" })}
      </p>
      <p className="text-8xl font-extralight tracking-tight tabular-nums">
        {date.toLocaleTimeString(locale, { hour: "2-digit", minute: "2-digit" })}
      </p>
    </div>
  );
}
