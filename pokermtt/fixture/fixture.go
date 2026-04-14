package fixture

import "fmt"

type ContractFixture struct {
	TournamentID string
	SourceMTTID  string
	DonorUserID  string
	MinerAddress string
	TableID      string
	HandNo       int
	SessionID    string
}

func DefaultContractFixture() ContractFixture {
	return ContractFixture{
		TournamentID: "poker-mtt-local-001",
		SourceMTTID:  "local-mtt-001",
		DonorUserID:  "7",
		MinerAddress: "claw1pokerfixture0000000000000000000000007",
		TableID:      "table-001",
		HandNo:       1,
		SessionID:    "session-001",
	}
}

func (fixture ContractFixture) HandID() string {
	return fmt.Sprintf("%s:%s:%d", fixture.TournamentID, fixture.TableID, fixture.HandNo)
}
