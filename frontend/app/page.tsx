"use client";

import React, { useState } from "react";

interface SquadPlayer {
  player_id: number;
  fpl_id: number;
  name: string;
  first_name: string;
  second_name: string;
  team: string;
  position: string;
  price: number;
  is_starting: boolean;
  is_captain: boolean;
  is_vice: boolean;
}

interface SquadResponse {
  user_id: number;
  fpl_entry_id: number;
  gameweek: number;
  squad: SquadPlayer[];
}

export default function Home() {
  const [fplId, setFplId] = useState<string>("1160158");
  const [apiPort, setApiPort] = useState<string>("8001");
  const [squadData, setSquadData] = useState<SquadResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(false);
  const [error, setError] = useState<string | null>(null);

  const fetchSquad = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!fplId.trim()) return;

    setLoading(true);
    setError(null);
    setSquadData(null);

    const backendUrl = `http://localhost:${apiPort}/squad/${fplId}`;

    try {
      const response = await fetch(backendUrl);
      if (!response.ok) {
        let errMsg = `Error ${response.status}: Failed to fetch squad.`;
        try {
          const errData = await response.json();
          if (errData && errData.detail) {
            errMsg = errData.detail;
          }
        } catch {
          // ignore
        }
        throw new Error(errMsg);
      }
      const data: SquadResponse = await response.json();
      setSquadData(data);
    } catch (err: any) {
      setError(err.message || "Something went wrong.");
    } finally {
      setLoading(false);
    }
  };

  // Group players by position in the standard FPL order
  const getPlayersByPosition = (position: string) => {
    if (!squadData) return [];
    return squadData.squad.filter((p) => p.position === position);
  };

  const positions = [
    { code: "GKP", label: "Goalkeepers" },
    { code: "DEF", label: "Defenders" },
    { code: "MID", label: "Midfielders" },
    { code: "FWD", label: "Forwards" },
  ];

  return (
    <main className="min-h-screen bg-slate-50 py-10 px-4 sm:px-6 lg:px-8 text-slate-800">
      <div className="max-w-4xl mx-auto">
        <h1 className="text-3xl font-extrabold text-slate-900 text-center mb-8">
          FergieTime Squad Viewer
        </h1>

        {/* Fetch Form */}
        <form
          onSubmit={fetchSquad}
          className="bg-white p-6 rounded-lg shadow-sm border border-slate-200 flex flex-wrap gap-4 items-end mb-8"
        >
          <div className="flex-1 min-w-[200px]">
            <label
              htmlFor="fplId"
              className="block text-sm font-medium text-slate-700 mb-1"
            >
              FPL Entry ID
            </label>
            <input
              type="text"
              id="fplId"
              value={fplId}
              onChange={(e) => setFplId(e.target.value)}
              placeholder="e.g. 1160158"
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>

          <div className="w-24">
            <label
              htmlFor="apiPort"
              className="block text-sm font-medium text-slate-700 mb-1"
            >
              API Port
            </label>
            <input
              type="text"
              id="apiPort"
              value={apiPort}
              onChange={(e) => setApiPort(e.target.value)}
              placeholder="8001"
              className="w-full px-3 py-2 border border-slate-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="px-5 py-2 bg-blue-600 hover:bg-blue-700 text-white font-medium rounded-md text-sm focus:outline-none focus:ring-2 focus:ring-blue-500 disabled:bg-blue-400 transition-colors cursor-pointer"
          >
            {loading ? "Loading..." : "Fetch Squad"}
          </button>
        </form>

        {/* Error Message */}
        {error && (
          <div className="bg-red-50 border-l-4 border-red-500 p-4 rounded-md mb-8">
            <div className="flex">
              <div className="flex-shrink-0">
                <svg
                  className="h-5 w-5 text-red-500"
                  viewBox="0 0 20 20"
                  fill="currentColor"
                >
                  <path
                    fillRule="evenodd"
                    d="M10 18a8 8 0 100-16 8 8 0 000 16zM8.707 7.293a1 1 0 00-1.414 1.414L8.586 10l-1.293 1.293a1 1 0 101.414 1.414L10 11.414l1.293 1.293a1 1 0 001.414-1.414L11.414 10l1.293-1.293a1 1 0 00-1.414-1.414L10 8.586 8.707 7.293z"
                    clipRule="evenodd"
                  />
                </svg>
              </div>
              <div className="ml-3">
                <p className="text-sm text-red-700 font-medium">{error}</p>
              </div>
            </div>
          </div>
        )}

        {/* Squad Display */}
        {squadData && (
          <div className="bg-white rounded-lg shadow-sm border border-slate-200 overflow-hidden">
            <div className="bg-slate-900 text-white px-6 py-4 flex justify-between items-center">
              <div>
                <h2 className="text-xl font-bold">
                  Manager Squad: {squadData.fpl_entry_id}
                </h2>
                <p className="text-xs text-slate-400">
                  Internal User ID: {squadData.user_id}
                </p>
              </div>
              <span className="bg-blue-600 px-3 py-1 rounded-full text-xs font-semibold">
                Gameweek {squadData.gameweek}
              </span>
            </div>

            <div className="p-6 space-y-8">
              {positions.map((pos) => {
                const players = getPlayersByPosition(pos.code);
                if (players.length === 0) return null;

                return (
                  <div key={pos.code}>
                    <h3 className="text-lg font-semibold text-slate-900 border-b border-slate-200 pb-2 mb-4">
                      {pos.label}
                    </h3>
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {players.map((player) => (
                        <div
                          key={player.player_id}
                          className="flex items-center justify-between p-4 border border-slate-100 rounded-lg hover:bg-slate-50 transition-colors"
                        >
                          <div>
                            <div className="flex items-center gap-2">
                              <span className="font-semibold text-slate-800">
                                {player.name}
                              </span>
                              <span className="text-xs text-slate-500 font-mono">
                                {player.first_name} {player.second_name}
                              </span>
                            </div>
                            <div className="text-xs text-slate-500 mt-1">
                              Team: <span className="font-medium text-slate-700">{player.team}</span> | Price:{" "}
                              <span className="font-medium text-slate-700">
                                £{(player.price / 10).toFixed(1)}m
                              </span>
                            </div>
                          </div>

                          <div className="flex gap-2">
                            {player.is_captain && (
                              <span className="bg-yellow-100 text-yellow-800 text-[10px] font-bold px-2 py-0.5 rounded border border-yellow-200">
                                C
                              </span>
                            )}
                            {player.is_vice && (
                              <span className="bg-slate-100 text-slate-800 text-[10px] font-bold px-2 py-0.5 rounded border border-slate-200">
                                V
                              </span>
                            )}
                            {player.is_starting ? (
                              <span className="bg-green-100 text-green-800 text-[10px] font-bold px-2.5 py-0.5 rounded-full">
                                Starting 11
                              </span>
                            ) : (
                              <span className="bg-amber-100 text-amber-800 text-[10px] font-bold px-2.5 py-0.5 rounded-full">
                                Bench
                              </span>
                            )}
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {!squadData && !loading && !error && (
          <div className="text-center py-12 text-slate-400 border-2 border-dashed border-slate-200 rounded-lg bg-white">
            Enter an FPL Entry ID and click "Fetch Squad" to display the squad layout.
          </div>
        )}
      </div>
    </main>
  );
}
