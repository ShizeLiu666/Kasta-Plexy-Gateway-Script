package main

import (
	"encoding/json"
	"fmt"
	"io/ioutil"
	"log"
	"net/http"
	"sync"
	"time"
)

const (
	gatewayIP  = "192.168.0.109"
	networkPIN = "13579246"
)

var (
	deviceCache []Device
	client      = &http.Client{Timeout: 10 * time.Second}
)

type Device struct {
	ID   string `json:"id"`
	Type string `json:"type"`
}

type CommandRequest struct {
	Attribute string `json:"attribute"`
	Value     bool   `json:"value"`
}

func getAllDevices() ([]Device, error) {
	if deviceCache != nil {
		return deviceCache, nil
	}

	url := fmt.Sprintf("http://%s/devices", gatewayIP)
	req, err := http.NewRequest("GET", url, nil)
	if err != nil {
		return nil, err
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", networkPIN))
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return nil, err
	}
	defer resp.Body.Close()

	body, err := ioutil.ReadAll(resp.Body)
	if err != nil {
		return nil, err
	}

	var result struct {
		Result []Device `json:"result"`
	}
	err = json.Unmarshal(body, &result)
	if err != nil {
		return nil, err
	}

	deviceCache = result.Result
	return deviceCache, nil
}

func sendControlCommand(deviceID string, attribute string, value bool) error {
	url := fmt.Sprintf("http://%s/devices/%s/commands", gatewayIP, deviceID)
	command := CommandRequest{Attribute: attribute, Value: value}
	jsonData, err := json.Marshal(command)
	if err != nil {
		return err
	}

	req, err := http.NewRequest("POST", url, bytes.NewBuffer(jsonData))
	if err != nil {
		return err
	}

	req.Header.Set("Authorization", fmt.Sprintf("Bearer %s", networkPIN))
	req.Header.Set("Content-Type", "application/json")

	resp, err := client.Do(req)
	if err != nil {
		return err
	}
	defer resp.Body.Close()

	if resp.StatusCode != http.StatusOK {
		return fmt.Errorf("failed to control device %s: status code %d", deviceID, resp.StatusCode)
	}

	return nil
}

func createScene(sceneName string, state bool) error {
	devices, err := getAllDevices()
	if err != nil {
		return err
	}

	var wg sync.WaitGroup
	errors := make(chan error, len(devices))

	for _, device := range devices {
		wg.Add(1)
		go func(d Device) {
			defer wg.Done()
			if err := sendControlCommand(d.ID, "status", state); err != nil {
				errors <- err
			}
			if d.Type == "dimmer" && state {
				if err := sendControlCommand(d.ID, "dimLevel", true); err != nil {
					errors <- err
				}
			}
		}(device)
	}

	wg.Wait()
	close(errors)

	for err := range errors {
		if err != nil {
			return fmt.Errorf("error in scene creation: %v", err)
		}
	}

	log.Printf("Scene %s creation completed", sceneName)
	return nil
}

func main() {
	for {
		fmt.Println("\nPlease select an option:")
		fmt.Println("1. Turn All On")
		fmt.Println("2. Turn All Off")
		fmt.Println("3. Exit")

		var choice int
		fmt.Scan(&choice)

		switch choice {
		case 1:
			err := createScene("Turn All On", true)
			if err != nil {
				log.Printf("Error: %v", err)
			} else {
				fmt.Println("Turn All On completed successfully")
			}
		case 2:
			err := createScene("Turn All Off", false)
			if err != nil {
				log.Printf("Error: %v", err)
			} else {
				fmt.Println("Turn All Off completed successfully")
			}
		case 3:
			fmt.Println("Exiting program")
			return
		default:
			fmt.Println("Invalid option, please try again")
		}
	}
}